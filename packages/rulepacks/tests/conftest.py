"""Builders for hand-written packages.

Tests here never touch an image. They construct ``ExtractedFields`` directly,
which is exactly the seam the engine is designed around: if a verdict cannot be
produced from these fields alone, it is not reproducible and not defensible.
"""

from __future__ import annotations

import pytest

from astra_rules import RulePack
from astra_schema import (
    CalibrationSource,
    ConsumerCare,
    ExtractedFields,
    FieldEvidence,
    Measurement,
    NetQuantity,
    Origin,
    PackDate,
    PackageGeometry,
    PackageShape,
    Price,
    Scale,
    Script,
    TextSpan,
)

PACK_ID = "lmpc-2011@2026.07.01"


@pytest.fixture(scope="session")
def pack() -> RulePack:
    return RulePack.load(PACK_ID)


def span(text: str, *, height_px: float = 30, width_px: float | None = None,
         confidence: float = 0.95, script: Script = Script.LATIN,
         scale: Scale | None = None) -> TextSpan:
    """One OCR token, optionally carrying a measured height."""
    width_px = width_px if width_px is not None else height_px * 0.6 * max(1, len(text))
    s = TextSpan(
        text=text,
        polygon=[(0, 0), (width_px, 0), (width_px, height_px), (0, height_px)],
        confidence=confidence,
        script=script,
        ink_height_px=height_px,
        ink_width_px=width_px,
    )
    if scale is not None:
        s.height = Measurement.from_pixels(height_px, scale)
        s.width = Measurement.from_pixels(width_px, scale)
    return s


def good_scale() -> Scale:
    """An ID-1 card in frame: the calibration we can defend."""
    return Scale.from_reference(
        measured_px=1000, known_mm=85.60, source=CalibrationSource.ID1_CARD,
        detail="ID-1 card long edge 1000 px",
    )


def barcode_scale() -> Scale:
    """An EAN-13 read as though printed at 100% magnification: not defensible."""
    return Scale.from_reference(
        measured_px=436, known_mm=37.29, source=CalibrationSource.BARCODE_ASSUMED,
    )


def compliant(**overrides) -> ExtractedFields:
    """A package that satisfies every rule in the pack.

    Every negative test starts from this and breaks exactly one thing, so a
    failure points at one rule rather than at the fixture.
    """
    scale = overrides.pop("scale", good_scale())
    # 40 px at this scale is ~3.4 mm, comfortably clear of the 2.5 mm required
    # for a 198 cm2 panel.
    f = ExtractedFields(
        scan_id="test-scan",
        image_sha256="0" * 64,
        scale=scale,
        full_text="sample package",
        ocr_scripts_seen=[Script.LATIN, Script.DEVANAGARI],
        geometry=PackageGeometry(
            shape=PackageShape.RECTANGULAR, height_mm=180, width_mm=110,
        ),
        manufacturer=FieldEvidence(
            present=True, confidence=0.9,
            raw_text="Packed by: Bharat Foods Pvt Ltd, Plot 14, MIDC, Pune 411018",
            spans=[span("Bharat Foods Pvt Ltd", scale=scale)],
        ),
        common_name=FieldEvidence(
            present=True, confidence=0.9, raw_text="Potato Chips",
            spans=[span("Potato Chips", scale=scale)],
        ),
        net_quantity=NetQuantity(
            present=True, confidence=0.95, raw_text="Net Quantity: 100 g",
            value=100.0, unit="g", canonical_unit="g", value_in_base=100.0,
            spans=[span("100 g", height_px=40, scale=scale)],
        ),
        mrp=Price(
            present=True, confidence=0.95,
            raw_text="Maximum Retail Price Rs 40.00 (inclusive of all taxes)",
            amount=40.0, has_inclusive_of_taxes_phrase=True, candidate_amounts=[40.0],
            spans=[span("Rs 40.00", height_px=40, scale=scale)],
        ),
        unit_sale_price=Price(
            present=True, confidence=0.8, raw_text="Rs 0.40 per g",
            amount=0.40, is_unit_sale_price=True,
            spans=[span("Rs 0.40 per g", scale=scale)],
        ),
        manufacture_date=PackDate(
            present=True, confidence=0.9, raw_text="Mfd: Aug 2026", month=8, year=2026,
            is_ambiguous=False, spans=[span("Aug 2026", scale=scale)],
        ),
        consumer_care=ConsumerCare(
            present=True, confidence=0.85,
            raw_text="Customer Care Manager, Plot 14, MIDC, Pune 411018. Tel 1800-123-4567",
            contact_name="Customer Care Manager", address="Plot 14, MIDC, Pune 411018",
            phone="1800-123-4567", email="care@bharatfoods.example",
            spans=[span("Customer Care Manager", scale=scale)],
        ),
        origin=Origin(present=True, confidence=0.9, raw_text="India",
                      country="India", is_imported=False),
        min_letter_height=Measurement.from_pixels(30, scale) if scale else None,
        declaration_contrast_ratio=12.4,
    )
    for key, value in overrides.items():
        setattr(f, key, value)
    return f
