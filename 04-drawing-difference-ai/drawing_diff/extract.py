"""PDF access layer.

Uses PyMuPDF when installed. Falls back to pypdfium2 + pdfplumber so the
project still runs where PyMuPDF (AGPL) is not wanted/available.
Coordinates for words are always PDF points, origin top-left.
"""
from __future__ import annotations

import io
import re
import statistics
from dataclasses import dataclass

import cv2
import numpy as np

try:  # preferred backend
    import pymupdf as fitz  # PyMuPDF (new import name)
except Exception:
    try:
        import fitz  # older PyMuPDF
    except Exception:  # pragma: no cover
        fitz = None

@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


def union_bbox(items):
    return (
        min(i.x0 for i in items),
        min(i.y0 for i in items),
        max(i.x1 for i in items),
        max(i.y1 for i in items),
    )


def group_lines(words: list[Word]) -> list[list[Word]]:
    """Group words into text lines in stable reading order (top->bottom, left->right).

    Re-ordering matters: CAD tools write text in content-stream order, which
    changes between revisions and would otherwise create false differences.
    """
    if not words:
        return []
    thick = [max(1.0, min(w.x1 - w.x0, w.y1 - w.y0)) for w in words]
    tol = max(2.0, 0.6 * statistics.median(thick))
    ordered = sorted(words, key=lambda w: ((w.y0 + w.y1) / 2, w.x0))
    lines: list[list[Word]] = []
    cur: list[Word] = []
    cur_y = None
    for w in ordered:
        yc = (w.y0 + w.y1) / 2
        if cur and abs(yc - cur_y) <= tol:
            cur.append(w)
            cur_y = sum((x.y0 + x.y1) / 2 for x in cur) / len(cur)
        else:
            if cur:
                lines.append(sorted(cur, key=lambda x: x.x0))
            cur = [w]
            cur_y = yc
    if cur:
        lines.append(sorted(cur, key=lambda x: x.x0))
    return lines


def reading_order(words: list[Word]) -> list[Word]:
    return [w for line in group_lines(words) for w in line]


def words_in(words: list[Word], box, margin: float = 12.0) -> list[Word]:
    x0, y0, x1, y1 = box
    return [
        w for w in reading_order(words)
        if w.x1 >= x0 - margin and w.x0 <= x1 + margin and w.y1 >= y0 - margin and w.y0 <= y1 + margin
    ]


SHEET_RE = re.compile(r"^[A-Z]{1,4}[-_./]?\d{2,4}[A-Z]?$")


def sheet_id(words: list[Word], width: float, height: float):
    """Guess the drawing/sheet number from the title block (bottom-right)."""
    cands = [w for w in words if w.x0 > 0.55 * width and w.y0 > 0.70 * height and SHEET_RE.match(w.text)]
    if not cands:
        return None
    cands.sort(key=lambda w: (bool(re.search(r"[-_./]", w.text)), len(w.text), w.y0))
    return cands[-1].text


class PdfDoc:
    def __init__(self, source, ocr: bool = False):
        if isinstance(source, (bytes, bytearray)):
            data = bytes(source)
        elif hasattr(source, "read"):
            data = source.read()
        else:
            with open(source, "rb") as f:
                data = f.read()
        self.data = data
        self.ocr = ocr
        if fitz is not None:
            self._f = fitz.open(stream=data, filetype="pdf")
            self.backend = "pymupdf"
            self.n_pages = len(self._f)
        else:
            import pdfplumber
            import pypdfium2 as pdfium

            self._pd = pdfium.PdfDocument(data)
            self._pl = pdfplumber.open(io.BytesIO(data))
            self.backend = "pdfium+pdfplumber"
            self.n_pages = len(self._pd)

    # -- geometry -------------------------------------------------------
    def size(self, i: int):
        if self.backend == "pymupdf":
            r = self._f[i].rect
            return float(r.width), float(r.height)
        p = self._pl.pages[i]
        return float(p.width), float(p.height)

    # -- text -----------------------------------------------------------
    def words(self, i: int) -> list[Word]:
        if self.backend == "pymupdf":
            out = [Word(w[4], w[0], w[1], w[2], w[3]) for w in self._f[i].get_text("words")]
        else:
            ws = self._pl.pages[i].extract_words(keep_blank_chars=False)
            out = [Word(w["text"], w["x0"], w["top"], w["x1"], w["bottom"]) for w in ws]
        out = [w for w in out if w.text.strip()]
        if not out and self.ocr:
            out = self._ocr_words(i)
        return out

    def _ocr_words(self, i: int) -> list[Word]:
        try:
            import pytesseract
        except Exception:
            return []
        dpi = 250
        img = self.render(i, dpi)
        d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        s = 72.0 / dpi
        res = []
        for t, x, y, w, h, c in zip(d["text"], d["left"], d["top"], d["width"], d["height"], d["conf"]):
            if t.strip() and float(c) > 40:
                res.append(Word(t.strip(), x * s, y * s, (x + w) * s, (y + h) * s))
        return res

    # -- raster ---------------------------------------------------------
    def render(self, i: int, dpi: int = 200) -> np.ndarray:
        """Return page as BGR uint8 image."""
        if self.backend == "pymupdf":
            pix = self._f[i].get_pixmap(dpi=dpi, alpha=False)
            arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)
            if pix.n == 1:
                return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
            return cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2BGR)
        bm = self._pd[i].render(scale=dpi / 72.0)
        arr = bm.to_numpy()
        if arr.ndim == 2:
            return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        return np.ascontiguousarray(arr[:, :, :3])  # pdfium gives BGR(A)
