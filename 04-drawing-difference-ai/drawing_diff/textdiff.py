"""Text-level diff on words or lines, keeping bounding boxes."""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .extract import Word, group_lines, union_bbox


@dataclass
class Unit:
    text: str
    bbox: tuple  # x0, y0, x1, y1 in PDF points


def to_units(words: list[Word], granularity: str) -> list[Unit]:
    if granularity == "line":
        units = []
        for line in group_lines(words):
            text = re.sub(r"\s+", " ", " ".join(w.text for w in line)).strip()
            if text:
                units.append(Unit(text, union_bbox(line)))
        return units
    out = []
    for line in group_lines(words):
        out.extend(Unit(w.text, (w.x0, w.y0, w.x1, w.y1)) for w in line)
    return out


def _bbox(units):
    if not units:
        return None
    return (
        min(u.bbox[0] for u in units),
        min(u.bbox[1] for u in units),
        max(u.bbox[2] for u in units),
        max(u.bbox[3] for u in units),
    )


def _mk(A, B):
    return dict(
        op="delete" if not B else "insert" if not A else "replace",
        old=" ".join(u.text for u in A),
        new=" ".join(u.text for u in B),
        bbox_a=_bbox(A),
        bbox_b=_bbox(B),
    )


def _shape(t: str) -> str:
    return re.sub(r"\d", "0", re.sub(r"[A-Za-z]", "A", t))


def _pair(A, B, threshold=0.5, shape_bonus=False):
    """Pair similar units inside a replace block (greedy by similarity).

    Stops unrelated neighbouring edits (e.g. a bolt count and a removed brace label)
    from being merged into one change.
    """
    out, used = [], set()
    for a in A:
        best, best_r = None, threshold
        for j, b in enumerate(B):
            if j in used:
                continue
            r = SequenceMatcher(None, a.text, b.text).ratio()
            if shape_bonus and _shape(a.text) == _shape(b.text):
                r = max(r, 0.6)
            if r > best_r:
                best, best_r = j, r
        if best is None:
            out.append(_mk([a], []))
        else:
            used.add(best)
            out.append(_mk([a], [B[best]]))
    out.extend(_mk([], [b]) for j, b in enumerate(B) if j not in used)
    return out


def diff_units(units_a: list[Unit], units_b: list[Unit], pair_lines: bool = False):
    ta = [u.text for u in units_a]
    tb = [u.text for u in units_b]
    sm = SequenceMatcher(None, ta, tb, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        A, B = units_a[i1:i2], units_b[j1:j2]
        if tag == "replace" and pair_lines:
            out.extend(_pair(A, B))
        elif tag == "replace" and len(A) > 1 or len(B) > 1 and tag == "replace":
            if len(A) >= 4 and len(B) >= 4:      # rewritten phrase/note: keep as one change
                out.append(_mk(A, B))
            else:
                out.extend(_pair(A, B, shape_bonus=True))
        else:
            out.append(_mk(A, B))
    return out
