"""End-to-end tests: a rendered image goes in, a cited report comes out.

These run the real OCR models, so they are slower than the rule-engine suite.
They earn that cost by covering the joins between calibration, measurement,
extraction and adjudication -- which is exactly where the bugs were: a card
detector that locked onto the package instead of the card, a unit sale price
read as a second MRP, a glyph width divided by its character count.

The measurement assertions are tight on purpose. Loose tolerances here would
let the geometry rot silently, and the geometry is the claim the whole project
stands on.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import synth  # noqa: E402

from astra_rules import evaluate  # noqa: E402
from astra_schema import CalibrationSource, FindingStatus, PackageShape  # noqa: E402
from vision.pipeline.analyse import analyse, decode  # noqa: E402
from vision.pipeline import calibration as calib  # noqa: E402

PACK = "lmpc-2011@2026.07.01"


def _analyse(png: bytes, truth: dict):
    return analyse(
        png,
        scan_id="e2e",
        shape=PackageShape.RECTANGULAR,
        height_mm=truth["package_height_mm"],
        width_mm=truth["package_width_mm"],
    )


@pytest.fixture(scope="module")
def compliant():
    png, truth = synth.compliant_label()
    return _analyse(png, truth), truth


@pytest.fixture(scope="module")
def undersized():
    png, truth = synth.undersized_label()
    return _analyse(png, truth), truth


# -- calibration -------------------------------------------------------------


def test_the_card_is_found_and_not_the_package():
    """The regression that mattered most.

    A 110 x 180 mm carton has an aspect of 1.64 against the ID-1 card's 1.586.
    Picking the largest card-shaped quadrilateral therefore selects the package,
    and every millimetre downstream comes out roughly threefold wrong.
    """
    png, truth = synth.compliant_label()
    calibration = calib.calibrate(decode(png))

    assert calibration.scale.source is CalibrationSource.ID1_CARD
    assert calibration.scale.is_usable_for_legal_assertion

    quad = calibration.reference_quad.reshape(-1, 2)
    width_px = quad[:, 0].max() - quad[:, 0].min()
    height_px = quad[:, 1].max() - quad[:, 1].min()
    assert width_px / height_px == pytest.approx(synth.ID1_LONG_MM / synth.ID1_SHORT_MM, rel=0.06)

    # The card sits below the package, so it must be in the lower half of frame.
    assert quad[:, 1].min() > decode(png).shape[0] * 0.5


def test_declared_dimensions_scale_against_the_package_not_the_photograph():
    """The declared width belongs to the package, not to the frame around it.

    Dividing by the full image width assumes the package fills the shot edge to
    edge. Any margin of background then understates every millimetre by however
    much of the photograph is not the package -- and understated millimetres are
    false violations. Here the package spans 110 of a 130 mm frame, so that
    mistake costs 15%, comfortably enough to invent a Rule 9 breach.
    """
    png, truth = synth.render(
        synth.LabelSpec(width_mm=110, height_mm=180, with_id1_card=False)
    )
    image = decode(png)
    true_mm_per_px = 1.0 / truth["px_per_mm"]

    calibration = calib.from_declared_dimension(image, 110.0)
    assert calibration is not None

    assert calibration.scale.mm_per_px == pytest.approx(true_mm_per_px, rel=0.03)

    # The stated uncertainty has to actually cover the error it makes.
    error = abs(calibration.scale.mm_per_px - true_mm_per_px) / true_mm_per_px
    assert error <= calibration.scale.relative_uncertainty


def test_a_declared_dimension_is_declined_when_the_package_cannot_be_located():
    """Better no scale than a scale measured against nothing."""
    blank = np.full((400, 400, 3), 245, dtype=np.uint8)
    assert calib.from_declared_dimension(blank, 110.0) is None


def test_a_label_with_no_reference_object_yields_no_usable_scale():
    png, _ = synth.render(synth.LabelSpec(with_id1_card=False))
    calibration = calib.calibrate(decode(png))
    assert not calibration.scale.is_usable_for_legal_assertion


# -- measurement accuracy ----------------------------------------------------


def test_net_quantity_height_is_recovered_to_a_fifth_of_a_millimetre(compliant):
    fields, truth = compliant
    measured = min(
        (s.height for s in fields.net_quantity.spans if s.height),
        key=lambda m: m.value_mm,
    )
    assert measured.value_mm == pytest.approx(truth["net_quantity_height_mm"], abs=0.2)


def test_the_true_height_lies_inside_the_reported_interval(compliant):
    """The interval has to mean something, or the INDETERMINATE gate is theatre."""
    fields, truth = compliant
    measured = min(
        (s.height for s in fields.net_quantity.spans if s.height),
        key=lambda m: m.value_mm,
    )
    assert measured.ci_low_mm <= truth["net_quantity_height_mm"] <= measured.ci_high_mm


def test_panel_area_matches_the_rendered_package(compliant):
    fields, truth = compliant
    assert fields.geometry.pdp_area_cm2 == pytest.approx(truth["pdp_area_cm2"], rel=0.02)


# -- extraction --------------------------------------------------------------


def test_every_mandatory_declaration_is_found(compliant):
    fields, _ = compliant
    for name in (
        "manufacturer", "common_name", "net_quantity", "mrp",
        "unit_sale_price", "manufacture_date", "consumer_care", "origin",
    ):
        assert getattr(fields, name).present, f"{name} was not extracted"


def test_declarations_are_read_correctly(compliant):
    fields, _ = compliant
    assert fields.net_quantity.value == 100
    assert fields.net_quantity.canonical_unit == "g"
    assert fields.mrp.amount == 40.0
    assert fields.mrp.has_inclusive_of_taxes_phrase
    assert fields.manufacture_date.month == 8
    assert fields.manufacture_date.year == 2026
    assert fields.origin.country == "India"
    assert fields.origin.is_imported is False
    assert fields.consumer_care.phone
    assert fields.consumer_care.address


def test_a_manufacturer_name_is_not_read_as_a_manufacturing_date(compliant):
    """'Manufactured by' introduces an address, never a date.

    Reading it as one would silently satisfy the month-and-year rule on a pack
    that carries no date at all -- a false negative, which is the failure mode
    an enforcement tool can least afford.
    """
    fields, _ = compliant
    assert fields.manufacture_date.raw_text
    assert "Bharat" not in (fields.manufacture_date.raw_text or "")


def test_the_common_name_is_not_stolen_from_another_declaration(compliant):
    fields, _ = compliant
    assert "Potato Chips" in (fields.common_name.raw_text or "")


def test_the_unit_sale_price_is_not_counted_as_a_second_mrp(compliant):
    """The mandatory unit sale price sits beside the retail price by design.

    Treating it as a rival MRP would report a dual-price violation on every
    compliant pack in the country.
    """
    fields, _ = compliant
    assert fields.mrp.candidate_amounts == [40.0]


# -- adjudication ------------------------------------------------------------


def test_a_compliant_label_produces_no_violations(compliant):
    fields, _ = compliant
    report = evaluate(fields, PACK)
    assert report.violations() == [], [
        (f.rule_id, f.measured, f.required) for f in report.violations()
    ]
    assert report.summary.verdict == "COMPLIANT"


def test_undersized_print_is_caught_with_the_right_threshold(undersized):
    fields, truth = undersized
    report = evaluate(fields, PACK)

    finding = next(f for f in report.findings if f.rule_id == "R9-T1-netqty-height")
    assert finding.status is FindingStatus.FAIL
    # 198 cm2 of panel puts this pack in the 100-500 band of Table-I.
    assert finding.required == "2.5 mm"
    assert finding.measurement.value_mm == pytest.approx(
        truth["net_quantity_height_mm"], abs=0.25
    )
    assert report.summary.critical_violations >= 1


def test_the_report_pins_the_rule_pack_and_the_image(compliant):
    fields, _ = compliant
    report = evaluate(fields, PACK)
    assert report.rulepack == PACK
    assert report.image_sha256 == fields.image_sha256
    assert len(report.image_sha256) == 64


def test_findings_carry_evidence_back_to_the_image(undersized):
    fields, _ = undersized
    report = evaluate(fields, PACK)
    violation = next(f for f in report.violations() if f.evidence)
    assert violation.evidence[0].image_sha256 == fields.image_sha256
    assert len(violation.evidence[0].polygon) == 4
