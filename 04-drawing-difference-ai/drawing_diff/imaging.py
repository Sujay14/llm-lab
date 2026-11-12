"""Alignment, visual diff and image helpers (OpenCV)."""
from __future__ import annotations

import cv2
import numpy as np


# ---------------------------------------------------------------- alignment
def align(a: np.ndarray, b: np.ndarray):
    """Register page B onto page A. Returns (aligned_b, mode).

    ORB + RANSAC homography, accepted only when it is a small, sane correction
    (same-CAD exports are normally already aligned; a wrong warp is worse than none).
    """
    h, w = a.shape[:2]
    if b.shape[:2] != (h, w):
        b = cv2.resize(b, (w, h), interpolation=cv2.INTER_AREA)
    try:
        ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
        orb = cv2.ORB_create(4000)
        k1, d1 = orb.detectAndCompute(ga, None)
        k2, d2 = orb.detectAndCompute(gb, None)
        if d1 is None or d2 is None or len(k1) < 40 or len(k2) < 40:
            return b, "identity"
        matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
        matches = sorted(matches, key=lambda m: m.distance)[:600]
        if len(matches) < 30:
            return b, "identity"
        src = np.float32([k2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
        dst = np.float32([k1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
        if H is None or int(mask.sum()) < 25:
            return b, "identity"
        scale = float(np.sqrt(abs(np.linalg.det(H[:2, :2]))))
        tx, ty = float(H[0, 2]), float(H[1, 2])
        persp = abs(H[2, 0]) + abs(H[2, 1])
        if abs(scale - 1) > 0.05 or max(abs(tx), abs(ty)) > 0.05 * max(h, w) or persp > 1e-3:
            return b, "identity"
        if abs(scale - 1) < 0.002 and max(abs(tx), abs(ty)) < 1.5:
            return b, "identity"  # already aligned; warping would only add noise
        out = cv2.warpPerspective(b, H, (w, h), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
        return out, "homography"
    except Exception:
        return b, "identity"


# -------------------------------------------------------------- visual diff
def visual_diff(a: np.ndarray, b: np.ndarray, dpi: int, min_ink: int | None = None):
    """Ink-based diff. Returns (regions, overlay_bgr).

    regions: list of dict(x, y, w, h, kind, ink_a, ink_b) in pixels (A space).
    Overlay: common ink gray, only-in-A red (removed), only-in-B green (added).
    """
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    ia = (ga < 200).astype(np.uint8)
    ib = (gb < 200).astype(np.uint8)
    tol = max(2, int(round(dpi / 100)))
    k = np.ones((2 * tol + 1, 2 * tol + 1), np.uint8)
    a_only = ia & (1 - cv2.dilate(ib, k))
    b_only = ib & (1 - cv2.dilate(ia, k))
    a_only = cv2.morphologyEx(a_only, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    b_only = cv2.morphologyEx(b_only, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    changed = a_only | b_only

    merge = int(dpi * 0.08) | 1
    blob = cv2.dilate(changed, np.ones((merge, merge), np.uint8))
    cnts, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_ink = min_ink if min_ink is not None else max(20, int(dpi * dpi / 2500))
    regions = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        ra = int(a_only[y:y + h, x:x + w].sum())
        rb = int(b_only[y:y + h, x:x + w].sum())
        if ra + rb < min_ink:
            continue
        kind = "removed" if rb < 0.2 * ra else "added" if ra < 0.2 * rb else "modified"
        regions.append(dict(x=x, y=y, w=w, h=h, kind=kind, ink_a=ra, ink_b=rb))

    overlay = np.full(a.shape, 255, np.uint8)
    common = (ia & (1 - a_only)).astype(bool)
    overlay[common] = (175, 175, 175)
    thick = np.ones((2, 2), np.uint8)
    overlay[cv2.dilate(a_only, thick).astype(bool)] = (0, 0, 230)
    overlay[cv2.dilate(b_only, thick).astype(bool)] = (0, 170, 0)
    return regions, overlay


# ------------------------------------------------------------ crop helpers
def crop_box(img, box, pad=40, min_w=260, min_h=150):
    """box = (x0, y0, x1, y1) in px. Pads, enforces a minimum size, clamps."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    if x1 - x0 < min_w:
        cx = (x0 + x1) / 2
        x0, x1 = cx - min_w / 2, cx + min_w / 2
    if y1 - y0 < min_h:
        cy = (y0 + y1) / 2
        y0, y1 = cy - min_h / 2, cy + min_h / 2
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(w, int(x1)), min(h, int(y1))
    if x1 <= x0 or y1 <= y0:
        return np.full((min_h, min_w, 3), 255, np.uint8)
    return img[y0:y1, x0:x1].copy()


def _fit(img, max_w=760, max_h=520):
    h, w = img.shape[:2]
    s = min(1.0, max_w / w, max_h / h)
    if s < 1.0:
        img = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    return img


def side_by_side(ca, cb):
    """Single composite image: A (old) on the left, B (new) on the right."""
    ca, cb = _fit(ca), _fit(cb)
    hh = max(ca.shape[0], cb.shape[0])

    def pad_to(im):
        out = np.full((hh, im.shape[1], 3), 255, np.uint8)
        out[: im.shape[0]] = im
        return out

    ca, cb = pad_to(ca), pad_to(cb)

    def header(width, text, color):
        bar = np.full((28, width, 3), 245, np.uint8)
        cv2.putText(bar, text, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
        return bar

    left = np.vstack([header(ca.shape[1], "A (old)", (0, 0, 200)), ca])
    right = np.vstack([header(cb.shape[1], "B (new)", (0, 130, 0)), cb])
    sep = np.full((left.shape[0], 6, 3), 120, np.uint8)
    return np.hstack([left, sep, right])


def png_bytes(img) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()
