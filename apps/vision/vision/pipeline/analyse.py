"""Image in, ``ExtractedFields`` out.

This module is the boundary of the probabilistic half of ASTRA. Everything it
produces is evidence with a confidence attached; nothing it produces is a
verdict. The rule engine is handed the result and decides on its own, which is
what lets a finding be replayed and explained months later.
"""

from __future__ import annotations

import hashlib
import logging
import math
import uuid

import cv2
import numpy as np

from astra_schema import (
    ExtractedFields,
    Measurement,
    PackageGeometry,
    PackageShape,
    PackageType,
    PrintMethod,
    ScanSource,
    TextSpan,
)

from . import calibration as calib
from . import extract, ocr

log = logging.getLogger(__name__)


def decode(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("could not decode image bytes")
    return image


def _estimate_package_extent(image: np.ndarray) -> tuple[float, float] | None:
    """Bounding box of the dominant foreground object, in pixels.

    Used to size the principal display panel when the inspector has not entered
    dimensions. It is a heuristic and it is treated as one: the geometry it
    produces is marked unconfident, and the PWA asks for a confirmation tap.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 120)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    biggest = max(contours, key=cv2.contourArea)
    frame_area = image.shape[0] * image.shape[1]
    if cv2.contourArea(biggest) < frame_area * 0.05:
        return None
    _, _, w, h = cv2.boundingRect(biggest)
    return float(w), float(h)


def _build_geometry(
    image: np.ndarray,
    scale,
    *,
    shape: PackageShape,
    print_method: PrintMethod,
    height_mm: float | None,
    width_mm: float | None,
    diameter_mm: float | None,
) -> PackageGeometry:
    geometry = PackageGeometry(
        shape=shape,
        print_method=print_method,
        height_mm=height_mm,
        width_mm=width_mm,
        diameter_mm=diameter_mm,
    )

    # Dimensions the inspector supplied always win over anything we infer.
    supplied = height_mm is not None and (width_mm is not None or diameter_mm is not None)
    if not supplied and scale is not None and scale.is_usable_for_legal_assertion:
        extent = _estimate_package_extent(image)
        if extent is not None:
            w_px, h_px = extent
            geometry.width_mm = geometry.width_mm or w_px * scale.mm_per_px
            geometry.height_mm = geometry.height_mm or h_px * scale.mm_per_px
            if shape is PackageShape.CYLINDRICAL and geometry.diameter_mm is None:
                # For a cylinder photographed side-on, the visible width is the
                # diameter.
                geometry.diameter_mm = geometry.width_mm

    geometry.pdp_area_cm2 = geometry.compute_pdp_area_cm2()
    geometry.pdp_area_confident = supplied and geometry.pdp_area_cm2 is not None
    return geometry


def _min_declaration_letter_height(fields: dict, spans: list[TextSpan]) -> Measurement | None:
    """Smallest measured glyph among the mandatory declarations.

    Only declaration text counts. Fine print of ingredients or a legal disclaimer
    is not what Rule 9 is about, and including it would produce violations on
    packs whose mandatory declarations are perfectly legible.
    """
    candidates: list[Measurement] = []
    for value in fields.values():
        for span in getattr(value, "spans", []) or []:
            if span.height is not None:
                candidates.append(span.height)
    if not candidates:
        return None
    return min(candidates, key=lambda m: m.value_mm)


def analyse(
    image_bytes: bytes,
    *,
    scan_id: str | None = None,
    scan_source: ScanSource = ScanSource.FIELD_INSPECTION,
    package_type: PackageType = PackageType.RETAIL,
    shape: PackageShape = PackageShape.OTHER,
    print_method: PrintMethod = PrintMethod.PRINTED,
    height_mm: float | None = None,
    width_mm: float | None = None,
    diameter_mm: float | None = None,
    commodity_category: str | None = None,
    is_perishable: bool = False,
    use_llm_normaliser: bool = False,
) -> ExtractedFields:
    """Analyse one label photograph."""
    image = decode(image_bytes)
    digest = hashlib.sha256(image_bytes).hexdigest()
    scan_id = scan_id or uuid.uuid4().hex

    calibration = calib.calibrate(image, package_width_mm=width_mm)
    # Measure on the rectified image when we have one: perspective compresses
    # glyphs horizontally and would otherwise invent width-ratio violations.
    working = calibration.rectified if calibration.rectified is not None else image

    spans = ocr.read(working, scale=calibration.scale)
    text = ocr.full_text(spans)
    extracted = extract.extract_all(text, spans)

    if use_llm_normaliser:
        from .llm import fill_gaps

        extracted = fill_gaps(text, extracted)

    geometry = _build_geometry(
        working,
        calibration.scale,
        shape=shape,
        print_method=print_method,
        height_mm=height_mm,
        width_mm=width_mm,
        diameter_mm=diameter_mm,
    )

    fields = ExtractedFields(
        scan_id=scan_id,
        image_sha256=digest,
        scale=calibration.scale if calibration.scale.source.value != "NONE" else None,
        full_text=text,
        ocr_scripts_seen=ocr.scripts_seen(spans),
        scan_source=scan_source,
        package_type=package_type,
        commodity_category=commodity_category,
        is_perishable=is_perishable,
        geometry=geometry,
        min_letter_height=_min_declaration_letter_height(extracted, spans),
        declaration_contrast_ratio=ocr.measure_declaration_contrast(working, spans),
        **extracted,
    )

    log.info(
        "scan %s: %d spans, calibrated via %s, %s",
        scan_id, len(spans), fields.scale.source if fields.scale else "NONE",
        f"PDP {geometry.pdp_area_cm2:.0f} cm2" if geometry.pdp_area_cm2 else "PDP unknown",
    )
    return fields
