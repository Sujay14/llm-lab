"""End-to-end comparison pipeline."""
from __future__ import annotations

import os
import time
from collections import Counter
from dataclasses import dataclass

import cv2

from .domains import get_domain
from .extract import PdfDoc, sheet_id, words_in
from .imaging import align, crop_box, png_bytes, side_by_side, visual_diff
from .llm import make_llm
from .textdiff import diff_units, to_units

SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class CompareOptions:
    domain: str = "tekla"            # generic | tekla | medical
    dpi: int = 200
    backend: str = "none"            # none | ollama | anthropic
    model: str | None = None
    ollama_host: str = "http://localhost:11434"
    llm_text: bool = False           # also let the LLM explain text changes (slower / costs more)
    visual: bool | None = None       # None = domain default
    ocr: bool = False                # OCR for scanned PDFs (needs pytesseract)
    match_by: str = "auto"           # auto (sheet number) | index
    max_regions: int = 25            # visual regions per page
    max_llm_calls: int = 80
    out_dir: str = "output"


def _match_pages(da, db, mode):
    ids_a = [sheet_id(da.words(i), *da.size(i)) for i in range(da.n_pages)]
    ids_b = [sheet_id(db.words(i), *db.size(i)) for i in range(db.n_pages)]
    pairs = []
    ok = (
        mode == "auto" and all(ids_a) and all(ids_b)
        and len(set(ids_a)) == len(ids_a) and len(set(ids_b)) == len(ids_b)
        and set(ids_a) & set(ids_b)
    )
    if ok:
        pos_b = {s: i for i, s in enumerate(ids_b)}
        used = set()
        for i, s in enumerate(ids_a):
            if s in pos_b:
                pairs.append((i, pos_b[s], s))
                used.add(pos_b[s])
            else:
                pairs.append((i, None, s))
        pairs += [(None, j, ids_b[j]) for j in range(db.n_pages) if j not in used]
    else:
        for i in range(max(da.n_pages, db.n_pages)):
            a = i if i < da.n_pages else None
            b = i if i < db.n_pages else None
            pairs.append((a, b, f"p{i + 1}"))
    return pairs


def _iou_cover(region, box):
    """fraction of region area covered by box (both x0,y0,x1,y1)."""
    ix = max(0, min(region[2], box[2]) - max(region[0], box[0]))
    iy = max(0, min(region[3], box[3]) - max(region[1], box[1]))
    area = max(1, (region[2] - region[0]) * (region[3] - region[1]))
    return ix * iy / area


def compare_pdfs(path_a, path_b, opts: CompareOptions | None = None, progress=None):
    opts = opts or CompareOptions()
    say = progress or (lambda msg, frac=None: None)
    t0 = time.time()
    domain = get_domain(opts.domain)
    use_visual = domain.visual if opts.visual is None else opts.visual
    llm = make_llm(opts.backend, opts.model, opts.ollama_host)
    img_dir = os.path.join(opts.out_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    da, db = PdfDoc(path_a, ocr=opts.ocr), PdfDoc(path_b, ocr=opts.ocr)
    pairs = _match_pages(da, db, opts.match_by)
    scale = opts.dpi / 72.0
    changes, pages = [], []
    llm_calls = 0

    def llm_describe(composite, ctx_a, ctx_b, change):
        nonlocal llm_calls
        if llm.name == "none" or llm_calls >= opts.max_llm_calls:
            return change
        llm_calls += 1
        try:
            d = llm.describe(png_bytes(composite), ctx_a, ctx_b, domain)
            if d:
                change.update({k: d[k] for k in ("change_type", "description", "severity", "confidence")})
                change["old"] = d["old"] or change.get("old")
                change["new"] = d["new"] or change.get("new")
                change["llm_used"] = True
        except Exception as e:  # keep going with rule-based result
            change["llm_error"] = str(e)[:200]
        return change

    for n, (ia, ib, label) in enumerate(pairs):
        say(f"Sheet {label} ({n + 1}/{len(pairs)})", n / max(1, len(pairs)))
        page = dict(label=label, index_a=ia, index_b=ib, matched=ia is not None and ib is not None,
                    n_changes=0, entity_summary=[], overlay=None, align="-")
        if ia is None or ib is None:
            changes.append(dict(page=label, page_index_a=ia, page_index_b=ib, source="sheet",
                                change_type="sheet_added" if ia is None else "sheet_removed",
                                description=f"Sheet {label} exists only in revision {'B' if ia is None else 'A'}",
                                old=None, new=None, severity="high", confidence=1.0, bbox_px=None, image=None))
            page["n_changes"] = 1
            pages.append(page)
            continue

        wa, wb = da.words(ia), db.words(ib)
        img_a, img_b = da.render(ia, opts.dpi), db.render(ib, opts.dpi)
        img_b_al, mode = align(img_a, img_b)
        page["align"] = mode
        page["entity_summary"] = domain.page_summary(wa, wb)
        page_changes = []

        # ---- 1. text changes -------------------------------------------
        text_boxes = []
        for t in diff_units(to_units(wa, domain.granularity), to_units(wb, domain.granularity),
                            pair_lines=domain.granularity == "line"):
            ba = t["bbox_a"] or t["bbox_b"]
            bb = t["bbox_b"] or t["bbox_a"]
            px_a = [v * scale for v in ba]
            px_b = [v * scale for v in bb]
            text_boxes += [[px_a[0] - 12, px_a[1] - 12, px_a[2] + 12, px_a[3] + 12],
                           [px_b[0] - 12, px_b[1] - 12, px_b[2] + 12, px_b[3] + 12]]
            pad = int(0.25 * opts.dpi)
            comp = side_by_side(crop_box(img_a, px_a, pad), crop_box(img_b, px_b, pad))
            c = domain.classify(t["old"], t["new"])
            c.update(page=label, page_index_a=ia, page_index_b=ib, source="text", llm_used=False,
                     bbox_px=[int(px_a[0]), int(px_a[1]), int(px_a[2] - px_a[0]), int(px_a[3] - px_a[1])])
            if opts.llm_text:
                ctx_a = " ".join(w.text for w in words_in(wa, ba)[:60])
                ctx_b = " ".join(w.text for w in words_in(wb, bb)[:60])
                c = llm_describe(comp, ctx_a, ctx_b, c)
            c["_comp"] = comp
            page_changes.append(c)

        # ---- 2. visual changes (not already explained by text) ---------
        overlay = None
        if use_visual:
            regions, overlay = visual_diff(img_a, img_b_al, opts.dpi)
            regions = [r for r in regions
                       if not any(_iou_cover((r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]), tb) >= 0.5
                                  for tb in text_boxes)]
            regions.sort(key=lambda r: r["ink_a"] + r["ink_b"], reverse=True)
            for r in regions[: opts.max_regions]:
                box = (r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"])
                pad = int(0.15 * opts.dpi)
                comp = side_by_side(crop_box(img_a, box, pad), crop_box(img_b_al, box, pad))
                mm = lambda px: px / opts.dpi * 25.4
                c = dict(page=label, page_index_a=ia, page_index_b=ib, source="visual",
                         change_type=f"{r['kind']}_element", severity="medium", confidence=0.6,
                         description=f"Graphic content {r['kind']} (region ~{mm(r['w']):.0f} x {mm(r['h']):.0f} mm)",
                         old=None, new=None, llm_used=False, bbox_px=[r["x"], r["y"], r["w"], r["h"]])
                pts = tuple(v / scale for v in box)
                ctx_a = " ".join(w.text for w in words_in(wa, pts)[:60])
                ctx_b = " ".join(w.text for w in words_in(wb, pts)[:60])
                c = llm_describe(comp, ctx_a, ctx_b, c)
                c["_comp"] = comp
                page_changes.append(c)
            if len(regions) > opts.max_regions:
                page["entity_summary"].append(
                    f"{len(regions) - opts.max_regions} additional small visual regions not listed (raise max_regions).")

        # ---- save images ------------------------------------------------
        safe = "".join(ch if ch.isalnum() else "_" for ch in label)
        for k, c in enumerate(page_changes):
            fn = f"{safe}_c{k + 1:03d}.png"
            cv2.imwrite(os.path.join(img_dir, fn), c.pop("_comp"))
            c["image"] = os.path.join("images", fn)
        if overlay is not None:
            fn = f"{safe}_overlay.jpg"
            h, w = overlay.shape[:2]
            s = min(1.0, 1600 / w)
            small = cv2.resize(overlay, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else overlay
            cv2.imwrite(os.path.join(img_dir, fn), small, [cv2.IMWRITE_JPEG_QUALITY, 82])
            page["overlay"] = os.path.join("images", fn)
        page["n_changes"] = len(page_changes)
        pages.append(page)
        changes.extend(page_changes)

    # ---- order, ids, stats ----------------------------------------------
    for i, c in enumerate(changes, 1):
        c["id"] = f"C{i:03d}"
    sev = Counter(c["severity"] for c in changes)
    typ = Counter(c["change_type"] for c in changes)
    result = dict(
        meta=dict(file_a=os.path.basename(str(path_a)), file_b=os.path.basename(str(path_b)),
                  domain=domain.name, dpi=opts.dpi, llm=llm.name, pdf_backend=da.backend,
                  visual_diff=use_visual, sheets_compared=len(pairs), llm_calls=llm_calls,
                  seconds=round(time.time() - t0, 1), disclaimer=domain.disclaimer),
        stats=dict(total=len(changes), by_severity=dict(sev), by_type=dict(typ)),
        pages=pages, changes=changes,
    )
    result["summary"] = _summary(result, llm, domain)
    say("Done", 1.0)
    return result


def _summary(result, llm, domain):
    ch = result["changes"]
    if llm.name != "none" and ch:
        try:
            ordered = sorted(ch, key=lambda c: SEV_ORDER[c["severity"]])
            s = llm.summarize(ordered, domain)
            if s:
                return s
        except Exception:
            pass
    st = result["stats"]
    if not ch:
        return "No differences detected between the two documents."
    sev = st["by_severity"]
    changed_pages = sum(1 for p in result["pages"] if p["n_changes"])
    top = ", ".join(f"{k} ({v})" for k, v in Counter(st["by_type"]).most_common(4))
    s = (f"{st['total']} change(s) across {changed_pages} of {len(result['pages'])} sheet(s): "
         f"{sev.get('high', 0)} high, {sev.get('medium', 0)} medium, {sev.get('low', 0)} low severity. "
         f"Most common: {top}.")
    highs = [c for c in sorted(ch, key=lambda c: SEV_ORDER[c["severity"]]) if c["severity"] == "high"][:5]
    if highs:
        s += " Key changes: " + "; ".join(f"[{c['page']}] {c['description']}" for c in highs) + "."
    return s
