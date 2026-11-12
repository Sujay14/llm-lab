"""PDF text extraction, page by page.

Design notes (learned from a real multi-report lab PDF):
* Every page keeps its real PDF page number. A printed label such as "Page 3 of 17" is kept
  separately because merged PDFs can contain several reports with their own numbering.
* "Card" pages (name, value and range grouped in boxes) read well in PyMuPDF's default block
  order. "Table" pages (Test | Result | Unit | Range) do not: the result lands far from the
  test name. For those pages we rebuild text row by row so each row stays together.
* Patient identifiers (name, lab/registration IDs, ...) are removed before indexing so they never
  reach the vector store, the prompt, the UI or the logs. This is best-effort hygiene only.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field

import pymupdf

import config
from utils.errors import NoTextError, PDFError

log = logging.getLogger(__name__)

REDACTED = "[REDACTED]"
_PRINTED_LABEL = re.compile(r"\bPage\s+(\d+)\s+of\s+(\d+)\b", re.IGNORECASE)

# Labels whose value is a patient identifier.
_ID_LABEL = (
    r"(?:patient\s*name|name|lab\s*id|regn?\.?\s*no\.?|ref\.?\s*no\.?|patient\s*id|uhid|mrn|"
    r"sample\s*id|barcode|phone|mobile|contact(?:\s*no\.?)?|address|e-?mail|dob|date\s*of\s*birth)"
)
_LABEL_ONLY = re.compile(rf"^\s*{_ID_LABEL}\s*:?\s*$", re.IGNORECASE)
_LABEL_VALUE = re.compile(rf"^\s*{_ID_LABEL}\s*:\s*(\S.*)$", re.IGNORECASE)
# Report-header fields (dates, centre, referrer): repeated on every page, useless for retrieval.
_HEADER = (
    r"(?:referred\s*by|ref\.?\s*by|sample\s*collec\w*(?:\s*date)?|regn\.?\s*date|print\s*date|"
    r"(?:regn\.?\s*)?cent(?:re|er))"
)
_HEADER_ONLY = re.compile(rf"^\s*{_HEADER}\s*:?\s*$", re.IGNORECASE)
_HEADER_LINE = re.compile(rf"^\s*{_HEADER}\s*(?:\||:)", re.IGNORECASE)
_NOISE_LINE = re.compile(r"^\s*(?:powered by.*|feedback)\s*$", re.IGNORECASE)
_NAME_LABEL = re.compile(r"^\s*(?:patient\s*)?name\s*:?", re.IGNORECASE)
_HONORIFIC = re.compile(r"^(?:mr|mrs|ms|miss|mx|dr|master|baby|smt|shri)\.?\s+", re.IGNORECASE)
# A value that is really just another field label (labels can sit on neighbouring lines).
_LOOKS_LIKE_LABEL = re.compile(
    r"(?:age|gender|sex|centre|center|date|referred|ref\.?\s*by|sample|print|regn|type)", re.IGNORECASE
)


@dataclass
class PageText:
    pdf_page: int                 # 1-based page number in the PDF viewer
    printed_label: str | None     # e.g. "Page 3 of 17" if the page prints one
    text: str


@dataclass
class ExtractionResult:
    pages: list[PageText]                 # only pages that still have readable content
    page_count: int                       # total pages in the PDF
    pages_without_text: list[int] = field(default_factory=list)
    identifiers_removed: int = 0


#layout helpers
def _row_text(page: pymupdf.Page, y_tol: float = 3.0, col_gap: float = 18.0) -> str:
    """Rebuild text row by row (words on the same baseline stay together; wide gaps -> ' | ')."""
    words = sorted(page.get_text("words"), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    rows: list[list[tuple]] = []
    row_y: float | None = None
    for w in words:
        y = (w[1] + w[3]) / 2
        if row_y is not None and abs(y - row_y) <= y_tol:
            rows[-1].append(w)
            row_y = (row_y + y) / 2
        else:
            rows.append([w])
            row_y = y
    lines = []
    for row in rows:
        row.sort(key=lambda w: w[0])
        parts = [row[0][4]]
        for prev, cur in zip(row, row[1:]):
            parts.append((" | " if cur[0] - prev[2] > col_gap else " ") + cur[4])
        lines.append("".join(parts))
    return "\n".join(lines)


def _is_table_page(row_text: str) -> bool:
    """True if a row looks like a results-table header, e.g. 'Test Name | Result | Unit | Range'."""
    for line in row_text.splitlines():
        cells = [c.strip(" :").lower() for c in line.split(" | ")]
        if len(cells) >= 3 and any(re.fullmatch(r"results?", c) for c in cells) and any(
            re.search(r"\b(unit|units|range|reference|interval)\b", c) for c in cells
        ):
            return True
    return False


def _clean(text: str) -> str:
    """Normalise whitespace only. Digits, decimal points, units and ranges are left untouched."""
    text = text.replace(" ", " ").replace("​", "")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return re.sub(r"\n{2,}", "\n", "\n".join(ln for ln in lines if ln)).strip()


# colour-dot markers
_HEADING = re.compile(r"^(?!You:)[A-Za-z(][A-Za-z0-9 ()/%.\-]{2,70}:\s*-?\d")
_LEGEND = re.compile(r"\((?:N|L|BL|H)\)")


def _dot_colour(fill) -> str | None:
    r, g, b = fill[:3]
    if r > 0.7 and g < 0.45 and b < 0.45:
        return "red"
    if g > r + 0.3 and g > b + 0.1:
        return "green"
    if r > 0.8 and g > 0.55 and b < 0.4:
        return "yellow/orange"
    return None  # black "You" arrows, logo pieces, etc.


def _annotate_markers(page: pymupdf.Page, text: str) -> str:
    """Some reports flag a result only with a coloured dot, which is invisible in extracted text.
    For each dot, find the result heading ('Name: 49.6 %') directly above it in the same column
    and append '[Report marker: red dot]' to that heading. Dots with no clear owner are skipped."""
    lines = []  # (x0, y0, y1, text) for every text line on the page
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            t = "".join(span["text"] for span in line["spans"])
            if t.strip():
                lines.append((line["bbox"][0], line["bbox"][1], line["bbox"][3], t))
    headings = [ln for ln in lines if _HEADING.match(ln[3])]
    legend_rows = [(y0, y1) for _, y0, y1, t in lines if _LEGEND.search(t)]
    drawings = page.get_drawings()
    pw, ph = page.rect.width, page.rect.height
    # Result "cards" are drawn as filled rectangles; ignore page-sized backgrounds.
    cards = [
        d["rect"] for d in drawings
        if d.get("fill") and d["rect"].width > 120 and d["rect"].height > 50
        and not (d["rect"].width > 0.9 * pw and d["rect"].height > 0.8 * ph)
    ]
    owned: dict[str, str] = {}
    for d in drawings:
        rect, fill = d["rect"], d.get("fill")
        if not fill or not (4 <= rect.width <= 12 and abs(rect.width - rect.height) < 1.5):
            continue
        colour = _dot_colour(fill)
        cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
        if colour is None or any(y0 - 3 <= cy <= y1 + 3 for y0, y1 in legend_rows):
            continue
        inside = [c for c in cards if c.x0 <= cx <= c.x1 and c.y0 <= cy <= c.y1]
        if not inside:
            continue  # no card around the dot: skip rather than guess
        card = min(inside, key=lambda c: c.width * c.height)  # innermost card
        cands = [
            h for h in headings
            if card.x0 - 2 <= h[0] <= cx and card.y0 - 2 <= h[1] <= cy + 5 and cy - h[1] <= 140
        ]
        if cands:
            owned.setdefault(max(cands, key=lambda h: h[1])[3], colour)  # nearest heading above the dot
    for heading, colour in owned.items():
        text = text.replace(heading, f"{heading} [Report marker: {colour} dot]", 1)
    return text

# ----------------------------------------------------------------------------- identifier removal
def _find_identifiers(raw_pages: list[str]) -> set[str]:
    """Collect identifier values that follow labels such as 'Name:' or 'Lab ID' on any page."""
    found: set[str] = set()
    for text in raw_pages:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for i, line in enumerate(lines):
            inline = _LABEL_VALUE.match(line)
            if inline:
                value = inline.group(1)
            elif _LABEL_ONLY.match(line):
                nxt = [ln for ln in lines[i + 1 : i + 3] if ln not in {":", "-"}]
                value = nxt[0].lstrip(": ").strip() if nxt else ""
            else:
                continue
            is_name = bool(_NAME_LABEL.match(line))
            if not value or len(value) > 60 or ":" in value or _LOOKS_LIKE_LABEL.search(value):
                continue
            if is_name:
                if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{1,59}", value) or len(value.split()) > 5:
                    continue
                bare = _HONORIFIC.sub("", value).strip()
                found.update({value, bare})
                found.update(t for t in re.split(r"[ .]+", bare) if len(t) >= 4)
            elif re.search(r"\d", value) and len(value) >= 4:  # IDs / phones contain digits
                found.add(value)
    return {v for v in found if len(v) >= 3}


def _strip_identifiers(text: str, identifiers: set[str]) -> tuple[str, int]:
    """Drop 'Label: value' lines and replace any remaining identifier value with [REDACTED]."""
    removed = 0
    kept: list[str] = []
    lines = text.splitlines()
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:  # value line that belonged to a dropped header label
            skip_next = False
            continue
        if _NOISE_LINE.match(line):
            continue
        if _HEADER_ONLY.match(line):  # label alone; its value is on the next line
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            skip_next = bool(nxt) and len(nxt) <= 40 and not nxt.rstrip().endswith(":") and not (
                _HEADER_ONLY.match(nxt) or _LABEL_ONLY.match(nxt)
            )
            continue
        if _HEADER_LINE.match(line):  # "Label | value" or "Label: value" on one line
            continue
        if _LABEL_ONLY.match(line) or _LABEL_VALUE.match(line):
            removed += 1
            continue
        kept.append(line)
    text = "\n".join(kept)
    for value in sorted(identifiers, key=len, reverse=True):
        text, n = re.subn(rf"(?<!\w){re.escape(value)}(?!\w)", REDACTED, text, flags=re.IGNORECASE)
        removed += n
    # Remove cells / lines that are nothing but a redaction (and an orphaned label before it).
    cleaned: list[str] = []
    for line in text.splitlines():
        if REDACTED in line:
            cells = [c for c in line.split(" | ")]
            out: list[str] = []
            for cell in cells:
                if REDACTED in cell:
                    if out and (_LABEL_ONLY.match(out[-1]) or out[-1].rstrip().endswith(":")):
                        out.pop()
                    continue
                out.append(cell)
            line = " | ".join(c for c in out if c.strip(" :"))
        if line.strip(" :|") and not _HEADER_LINE.match(line):  # rows exposed by cell removal
            cleaned.append(line)
    return "\n".join(cleaned), removed


def _drop_repeated_boilerplate(texts: list[str]) -> list[str]:
    """Remove long lines repeated on many pages (letterheads, footers, disclaimers).

    Only lines of 40+ characters qualify, so short but meaningful repeats such as
    'NORMAL' or 'METHOD: CALCULATED' are never removed.
    """
    if len(texts) < 4:
        return texts
    counts: Counter[str] = Counter()
    for t in texts:
        counts.update({ln for ln in t.splitlines() if len(ln) >= 40})
    threshold = max(3, int(len(texts) * 0.4))
    repeated = {ln for ln, c in counts.items() if c >= threshold}
    return ["\n".join(ln for ln in t.splitlines() if ln not in repeated) for t in texts]


# public API
def extract_pages(pdf_bytes: bytes) -> ExtractionResult:
    """Extract readable text per page. Raises PDFError / NoTextError with friendly messages."""
    if not pdf_bytes:
        raise PDFError("The uploaded file is empty.")
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        log.error("Could not open PDF (%s)", type(exc).__name__)
        raise PDFError("This file could not be opened as a PDF. It may be corrupt or not a real PDF.") from exc

    with doc:
        if doc.needs_pass or doc.is_encrypted:
            raise PDFError("This PDF is password-protected. Please remove the password and upload it again.")
        if doc.page_count == 0:
            raise PDFError("This PDF has no pages.")
        if doc.page_count > config.MAX_PAGES:
            raise PDFError(f"This PDF has {doc.page_count} pages; the limit is {config.MAX_PAGES}.")

        raw_pages: list[str] = []
        labels: list[str | None] = []
        try:
            for page in doc:
                default_text = page.get_text("text")
                m = _PRINTED_LABEL.search(default_text)
                labels.append(f"Page {m.group(1)} of {m.group(2)}" if m else None)
                rows = _row_text(page)
                raw_pages.append(rows if _is_table_page(rows) else _annotate_markers(page, default_text))
        except Exception as exc:  # noqa: BLE001
            log.error("Text extraction failed (%s)", type(exc).__name__)
            raise PDFError("Text could not be read from this PDF. It may be damaged.") from exc
        page_count = doc.page_count

    cleaned = [_clean(_PRINTED_LABEL.sub("", t)) for t in raw_pages]
    identifiers = _find_identifiers(cleaned)
    removed_total = 0
    stripped: list[str] = []
    for t in cleaned:
        t2, n = _strip_identifiers(t, identifiers)
        stripped.append(t2)
        removed_total += n
    stripped = [_clean(t) for t in _drop_repeated_boilerplate(stripped)]

    has_content = [len(t) >= config.MIN_PAGE_CHARS for t in stripped]  # ignore header-only pages
    pages = [PageText(i, labels[i - 1], t) for i, (t, ok) in enumerate(zip(stripped, has_content), start=1) if ok]
    empty = [i for i, ok in enumerate(has_content, start=1) if not ok]

    if sum(len(p.text) for p in pages) < config.MIN_TEXT_CHARS:
        raise NoTextError(
            "No selectable text was found in this PDF. It looks like a scanned or image-only report. "
            "OCR (reading text from images) is not included in this version."
        )
    log.info("Extracted %d/%d pages with text; %d identifier items removed", len(pages), page_count, removed_total)
    return ExtractionResult(pages, page_count, empty, removed_total)
