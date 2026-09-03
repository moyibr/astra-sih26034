"""Measuring glyphs and contrast inside an OCR box.

Rule 9 talks about the height of a numeral or a letter. A text detector gives us
a *bounding box*, which is a different thing: it includes leading, ascenders and
descenders, and is routinely 20-40% taller than the glyphs inside it. Measuring
the box instead of the ink would systematically flatter non-compliant labels and
let genuinely tiny print pass, so everything here works on ink.
"""

from __future__ import annotations

import cv2
import numpy as np

# Connected components smaller than this fraction of the crop are treated as
# noise -- JPEG speckle, the dot on an i, a stray comma.
_MIN_COMPONENT_AREA_FRAC = 0.004


def binarise(crop_gray: np.ndarray) -> tuple[np.ndarray, bool]:
    """Separate ink from background.

    Returns a mask where True is ink, plus whether the ink was darker than the
    background. Labels print both ways round -- black on white and white on a
    dark panel -- and Otsu alone cannot tell which side is which, so we decide
    from the border, which is almost always background.
    """
    blurred = cv2.GaussianBlur(crop_gray, (3, 3), 0)
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    border = np.concatenate([otsu[0, :], otsu[-1, :], otsu[:, 0], otsu[:, -1]])
    background_is_bright = border.mean() > 127

    ink = (otsu == 0) if background_is_bright else (otsu == 255)
    return ink, background_is_bright


def glyph_metrics(crop_gray: np.ndarray, *, digits_only: bool = False) -> tuple[float, float] | None:
    """Return (representative glyph height, mean glyph width) in pixels.

    Individual characters are recovered as connected components. The reported
    height is the **median** component height rather than the maximum: a single
    tall capital, a bracket or a rupee sign would otherwise speak for a whole
    declaration set in much smaller type.

    ``digits_only`` biases towards the taller cluster of components, since
    numerals sit at cap height while lower-case letters do not -- useful when a
    span like ``100 g`` mixes the two and the rule is about the numerals.
    """
    if crop_gray.size == 0 or min(crop_gray.shape[:2]) < 3:
        return None

    ink, _ = binarise(crop_gray)
    mask = ink.astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        return None

    crop_area = crop_gray.shape[0] * crop_gray.shape[1]
    heights: list[float] = []
    widths: list[float] = []
    for i in range(1, count):
        w = float(stats[i, cv2.CC_STAT_WIDTH])
        h = float(stats[i, cv2.CC_STAT_HEIGHT])
        area = float(stats[i, cv2.CC_STAT_AREA])
        if area < crop_area * _MIN_COMPONENT_AREA_FRAC:
            continue
        # A component spanning nearly the whole crop is usually a border or an
        # underline that got joined to the text, not a glyph.
        if h >= crop_gray.shape[0] * 0.98 and w >= crop_gray.shape[1] * 0.9:
            continue
        heights.append(h)
        widths.append(w)

    if not heights:
        return None

    heights_arr = np.array(heights)
    if digits_only and len(heights_arr) >= 3:
        # Numerals occupy the taller band; take the upper cluster's median.
        cutoff = np.percentile(heights_arr, 50)
        tall = heights_arr[heights_arr >= cutoff]
        height = float(np.median(tall))
    else:
        height = float(np.median(heights_arr))

    return height, float(np.mean(widths))


def _relative_luminance(bgr: np.ndarray) -> float:
    """WCAG 2.x relative luminance from an OpenCV BGR triple."""
    b, g, r = (np.clip(bgr, 0, 255) / 255.0)

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(crop_bgr: np.ndarray) -> float | None:
    """Luminance contrast between the ink and its immediate background.

    Rule 9 requires a colour that contrasts "conspicuously" and names no figure.
    This turns the phrase into a number an officer can put in a notice; the
    threshold applied to it is a published WCAG proxy, and the generated finding
    says so rather than implying the statute states one.
    """
    if crop_bgr.size == 0 or min(crop_bgr.shape[:2]) < 3:
        return None

    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    ink, _ = binarise(gray)
    if ink.sum() < 8 or (~ink).sum() < 8:
        return None

    # Percentiles, not medians. In small print most "ink" pixels are actually
    # anti-aliased blends of ink and background, so a median drags the two
    # populations towards each other and understates the contrast of type that
    # is in fact perfectly legible. We take the core of each population: the
    # darkest quarter of the ink and the lightest quarter of the background,
    # swapping when the label is printed light-on-dark.
    ink_lum = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    ink_dark = ink_lum[ink].mean() < ink_lum[~ink].mean()

    def core(pixels: np.ndarray, take_dark: bool) -> np.ndarray:
        lum = pixels.astype(np.float32) @ np.array([0.114, 0.587, 0.299], dtype=np.float32)
        cutoff = np.percentile(lum, 25 if take_dark else 75)
        keep = lum <= cutoff if take_dark else lum >= cutoff
        return np.median(pixels[keep], axis=0) if keep.any() else np.median(pixels, axis=0)

    ink_colour = core(crop_bgr[ink], ink_dark)
    bg_colour = core(crop_bgr[~ink], not ink_dark)

    l1 = _relative_luminance(ink_colour)
    l2 = _relative_luminance(bg_colour)
    lighter, darker = max(l1, l2), min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def crop_polygon(image: np.ndarray, polygon: list[tuple[float, float]], pad: int = 2) -> np.ndarray:
    """Axis-aligned crop around a detection polygon, with a little padding."""
    pts = np.array(polygon, dtype=np.float32)
    x0 = max(0, int(pts[:, 0].min()) - pad)
    y0 = max(0, int(pts[:, 1].min()) - pad)
    x1 = min(image.shape[1], int(np.ceil(pts[:, 0].max())) + pad)
    y1 = min(image.shape[0], int(np.ceil(pts[:, 1].max())) + pad)
    if x1 <= x0 or y1 <= y0:
        return np.empty((0, 0), dtype=image.dtype)
    return image[y0:y1, x0:x1]
