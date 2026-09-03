"""Text detection and recognition.

RapidOCR runs the PP-OCR models on ONNX Runtime. That choice is deliberate: it
gives the same recognition quality as PaddleOCR, including Devanagari, without
dragging in the PaddlePaddle runtime -- which matters because the whole system
has to install cleanly on a teammate's Windows laptop and inside a container that
runs offline at the venue.

Every recognised token comes back as a ``TextSpan`` carrying its polygon, its
confidence, the script it is written in, and -- once a scale is known -- the
measured height of the ink inside it.
"""

from __future__ import annotations

import functools
import logging
import re

import numpy as np

from astra_schema import Measurement, Scale, Script, TextSpan

from .measure import contrast_ratio, crop_polygon, glyph_metrics

log = logging.getLogger(__name__)

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")


@functools.lru_cache(maxsize=1)
def _engine():
    """Build the OCR engine once; it is expensive and thread-safe to reuse."""
    from rapidocr import RapidOCR

    return RapidOCR()


def detect_script(text: str) -> Script:
    if _DEVANAGARI.search(text):
        return Script.DEVANAGARI
    if _LATIN.search(text):
        return Script.LATIN
    return Script.OTHER


def read(
    image_bgr: np.ndarray,
    *,
    scale: Scale | None = None,
    min_confidence: float = 0.3,
) -> list[TextSpan]:
    """Recognise every text region and measure the ink inside each one.

    ``min_confidence`` drops detections we would not rely on anyway. It is set
    low on purpose: the rule engine decides what confidence is sufficient for
    each individual rule, and it can only do that if we hand it the evidence.
    """
    try:
        result = _engine()(image_bgr)
    except Exception:
        log.exception("OCR failed")
        return []

    if result is None or not getattr(result, "txts", None):
        return []

    gray = None
    spans: list[TextSpan] = []

    for box, text, score in zip(result.boxes, result.txts, result.scores):
        if not text or score < min_confidence:
            continue

        polygon = [(float(x), float(y)) for x, y in np.asarray(box).reshape(-1, 2)[:4]]
        if len(polygon) != 4:
            continue

        span = TextSpan(
            text=str(text),
            polygon=polygon,
            confidence=float(score),
            script=detect_script(str(text)),
        )

        if gray is None:
            import cv2

            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

        crop = crop_polygon(gray, polygon)
        metrics = glyph_metrics(crop, digits_only=any(c.isdigit() for c in span.text))
        if metrics is not None:
            span.ink_height_px, span.ink_width_px = metrics
            if scale is not None:
                span.height = Measurement.from_pixels(span.ink_height_px, scale)
                span.width = Measurement.from_pixels(span.ink_width_px, scale)

        spans.append(span)

    log.info("read %d spans", len(spans))
    return spans


def scripts_seen(spans: list[TextSpan]) -> list[Script]:
    """Which scripts actually carry content, ignoring stray single characters."""
    counts: dict[Script, int] = {}
    for s in spans:
        if len(s.text.strip()) >= 2:
            counts[s.script] = counts.get(s.script, 0) + 1
    return [script for script, n in counts.items() if n >= 1]


def measure_declaration_contrast(image_bgr: np.ndarray, spans: list[TextSpan]) -> float | None:
    """Worst contrast among the text regions, which is what the rule cares about.

    A label whose brand name is bold black and whose MRP is pale grey complies on
    average and fails where it matters, so we report the minimum rather than the
    mean.
    """
    ratios: list[float] = []
    for span in spans:
        crop = crop_polygon(image_bgr, span.polygon)
        ratio = contrast_ratio(crop)
        if ratio is not None:
            ratios.append(ratio)
    if not ratios:
        return None
    return min(ratios)


def full_text(spans: list[TextSpan]) -> str:
    """Reading-order-ish concatenation, top to bottom then left to right."""
    ordered = sorted(spans, key=lambda s: (min(p[1] for p in s.polygon), min(p[0] for p in s.polygon)))
    return "\n".join(s.text for s in ordered)
