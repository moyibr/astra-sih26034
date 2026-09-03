"""Behavioural tests for the rule engine.

The suite is organised around the four outcomes a rule can produce, because the
interesting behaviour of this system is not "does it spot a violation" -- that is
easy -- but "does it refuse to spot one when it cannot actually tell".
"""

from __future__ import annotations

import pytest

from astra_rules import RulePack, evaluate
from astra_schema import (
    ConsumerCare,
    FindingStatus,
    Measurement,
    NetQuantity,
    Origin,
    PackDate,
    PackageGeometry,
    PackageShape,
    PackageType,
    Price,
    ScanSource,
    Script,
    Severity,
)

from label_fixtures import PACK_ID, barcode_scale, compliant, good_scale, span


def status_of(report, rule_id: str) -> FindingStatus:
    return next(f for f in report.findings if f.rule_id == rule_id).status


def finding(report, rule_id: str):
    return next(f for f in report.findings if f.rule_id == rule_id)


# -- baseline ----------------------------------------------------------------


def test_compliant_package_has_no_violations():
    report = evaluate(compliant(), PACK_ID)
    assert report.summary.verdict == "COMPLIANT"
    assert report.summary.failed == 0
    assert report.summary.compliance_score == 100.0


def test_report_pins_the_pack_that_judged_it():
    report = evaluate(compliant(), PACK_ID)
    assert report.rulepack == "lmpc-2011@2026.07.01"


def test_every_rule_in_the_pack_is_reported_on(pack: RulePack):
    report = evaluate(compliant(), PACK_ID)
    assert {f.rule_id for f in report.findings} == {r.id for r in pack.rules}


# -- Rule 6(1): missing declarations -----------------------------------------


def test_missing_mrp_is_a_critical_violation():
    report = evaluate(compliant(mrp=Price()), PACK_ID)
    assert status_of(report, "R6-1-e-mrp") is FindingStatus.FAIL
    assert report.summary.critical_violations >= 1
    assert report.summary.verdict == "NON_COMPLIANT"


def test_a_missing_price_does_not_also_fault_its_wording():
    """One defect, one finding.

    Without prerequisites, a missing price would fail three rules at once and
    triple-count a single underlying problem in the officer's queue.
    """
    report = evaluate(compliant(mrp=Price()), PACK_ID)
    assert status_of(report, "R6-1-e-mrp") is FindingStatus.FAIL
    assert status_of(report, "R6-1-e-mrp-inclusive") is FindingStatus.NOT_APPLICABLE
    assert status_of(report, "R6-1-e-dual-mrp") is FindingStatus.NOT_APPLICABLE


def test_mrp_without_inclusive_of_taxes_wording():
    fields = compliant()
    fields.mrp.has_inclusive_of_taxes_phrase = False
    report = evaluate(fields, PACK_ID)
    assert status_of(report, "R6-1-e-mrp-inclusive") is FindingStatus.FAIL


def test_low_confidence_reading_is_indeterminate_not_a_violation():
    """A faint reading is a reason to look again, not a reason to prosecute."""
    fields = compliant()
    fields.manufacturer.confidence = 0.20
    report = evaluate(fields, PACK_ID)
    assert status_of(report, "R6-1-a-manufacturer") is FindingStatus.INDETERMINATE


# -- Scenario: dual MRP (the e-commerce price scam) --------------------------


def test_two_different_prices_on_one_pack_is_a_violation():
    fields = compliant()
    fields.mrp.candidate_amounts = [40.0, 60.0]
    report = evaluate(fields, PACK_ID)
    f = finding(report, "R6-1-e-dual-mrp")
    assert f.status is FindingStatus.FAIL
    assert f.severity is Severity.CRITICAL
    assert "40" in f.measured and "60" in f.measured


# -- Scenario: the unit symbol ('100 gms.') ----------------------------------


@pytest.mark.parametrize("printed,expected", [("g", True), ("kg", True), ("ml", True)])
def test_correct_si_symbols_pass(printed, expected):
    fields = compliant()
    fields.net_quantity.unit = printed
    assert (status_of(evaluate(fields, PACK_ID), "R6-1-c-unit-symbol") is FindingStatus.PASS) is expected


@pytest.mark.parametrize("printed,symbol", [("gms.", "g"), ("gm", "g"), ("Kgs", "kg"), ("ltr", "l")])
def test_irregular_unit_symbols_are_flagged_but_only_as_advisory(printed, symbol):
    """The direction is right, the severity is not.

    Ranking 'gms.' alongside a missing MRP would bury real consumer harm under
    typography and cost the tool its credibility with the officer using it.
    """
    fields = compliant()
    fields.net_quantity.unit = printed
    report = evaluate(fields, PACK_ID)
    f = finding(report, "R6-1-c-unit-symbol")
    assert f.status is FindingStatus.FAIL
    assert f.severity is Severity.ADVISORY
    assert f.required == symbol
    assert report.summary.critical_violations == 0
    assert report.summary.verdict == "PARTIALLY_COMPLIANT"


# -- Scenario: font height (the rule everyone quotes wrongly) ----------------


def test_font_height_threshold_comes_from_panel_area_not_net_weight():
    """A 100 g pack attracts 1.0 mm or 2.5 mm depending only on its panel.

    This is the provision most commonly misquoted as being keyed to net weight.
    Both packs below hold exactly 100 g; only the panel area differs.
    """
    pack = RulePack.load(PACK_ID)
    table = pack.tables["table_I"]
    from astra_schema import PrintMethod

    small_panel, _ = table.threshold_for(40, PrintMethod.PRINTED)    # 40 cm2
    large_panel, _ = table.threshold_for(198, PrintMethod.PRINTED)   # 198 cm2
    assert small_panel == 1.0
    assert large_panel == 2.5


def test_undersized_numerals_fail_when_the_scale_is_trustworthy():
    scale = good_scale()
    fields = compliant(scale=scale)
    # 12 px at ~0.0856 mm/px is ~1.03 mm, well under the 2.5 mm this panel needs.
    fields.net_quantity.spans = [span("100 g", height_px=12, scale=scale)]
    report = evaluate(fields, PACK_ID)
    f = finding(report, "R9-T1-netqty-height")
    assert f.status is FindingStatus.FAIL
    assert f.required == "2.5 mm"
    assert f.measurement is not None and f.measurement.value_mm == pytest.approx(1.03, abs=0.05)


def test_identical_pixels_do_not_convict_when_only_a_barcode_calibrated_them():
    """The same photograph, the same glyph, a worse ruler.

    An EAN-13 may legally be printed anywhere from 80% to 200% magnification, so
    reading one as though it were 100% can be wrong by a factor of two. The
    engine must decline to convict on that, however damning the midpoint looks.
    """
    scale = barcode_scale()
    fields = compliant(scale=scale)
    fields.net_quantity.spans = [span("100 g", height_px=12, scale=scale)]
    fields.min_letter_height = Measurement.from_pixels(12, scale)

    report = evaluate(fields, PACK_ID)
    assert status_of(report, "R9-T1-netqty-height") is FindingStatus.INDETERMINATE
    assert report.calibration_note is not None
    assert "ID-card-sized" in report.calibration_note


def test_tiny_print_is_still_convictable_with_a_good_ruler():
    """The gate is on the ruler, not on the width of the answer.

    Two pixels of doubt on a 1.2 mm glyph is more than 10% of it. A gate applied
    to the combined interval would therefore refuse to convict on precisely the
    tiny lettering Rule 9 exists to catch -- even with an ID-1 card in frame and
    the entire interval sitting a millimetre clear of the threshold.
    """
    scale = good_scale()
    fields = compliant(scale=scale)
    fields.net_quantity.spans = [span("100 g", height_px=14, scale=scale)]

    measurement = fields.net_quantity.spans[0].height
    # Imprecise in relative terms...
    assert measurement.relative_uncertainty > 0.10
    # ...but measured with a ruler we trust, and decisive all the same.
    assert measurement.scale_uncertainty <= 0.10
    assert measurement.ci_high_mm < 2.5

    assert status_of(evaluate(fields, PACK_ID), "R9-T1-netqty-height") is FindingStatus.FAIL


def test_the_interval_widens_for_small_glyphs():
    """Absolute reading error does not shrink just because the print does."""
    scale = good_scale()
    big = span("100 g", height_px=60, scale=scale).height
    small = span("100 g", height_px=12, scale=scale).height

    def half_width(m):
        return m.ci_high_mm - m.value_mm

    # The absolute margin is comparable, so as a share of the value it is far
    # larger on the smaller glyph.
    assert small.relative_uncertainty > big.relative_uncertainty * 2


def test_no_scale_at_all_leaves_measurement_rules_undecided():
    fields = compliant(scale=None)
    fields.min_letter_height = None
    report = evaluate(fields, PACK_ID)
    assert status_of(report, "R9-T1-netqty-height") is FindingStatus.INDETERMINATE
    assert status_of(report, "R9-letter-height") is FindingStatus.INDETERMINATE
    assert report.summary.verdict == "NEEDS_REVIEW"


def test_unknown_panel_area_leaves_the_height_rule_undecided():
    fields = compliant()
    fields.geometry = PackageGeometry(shape=PackageShape.OTHER)
    report = evaluate(fields, PACK_ID)
    f = finding(report, "R9-T1-netqty-height")
    assert f.status is FindingStatus.INDETERMINATE
    assert "principal display panel" in f.explanation


# -- Scenario: consumer care details -----------------------------------------


def test_consumer_care_with_only_an_email_is_incomplete():
    fields = compliant(
        consumer_care=ConsumerCare(
            present=True, confidence=0.8,
            raw_text="For complaints, contact manager at feedback@email.example",
            email="feedback@email.example",
        )
    )
    f = finding(evaluate(fields, PACK_ID), "R6-1-f-consumer-care")
    assert f.status is FindingStatus.FAIL
    assert "postal address" in f.explanation


def test_consumer_care_with_name_address_and_one_channel_is_enough():
    fields = compliant(
        consumer_care=ConsumerCare(
            present=True, confidence=0.8, raw_text="...",
            contact_name="Grievance Officer", address="12 MG Road, Bengaluru 560001",
            phone="080-12345678",
        )
    )
    assert status_of(evaluate(fields, PACK_ID), "R6-1-f-consumer-care") is FindingStatus.PASS


# -- Scenario: the ambiguous date --------------------------------------------


def test_a_plain_dd_mm_yyyy_date_is_not_treated_as_a_violation():
    """05-08-2027 alone is lawful and ubiquitous in India.

    Flagging every hyphenated date would generate enormous false positives and
    train officers to ignore the tool.
    """
    fields = compliant(
        manufacture_date=PackDate(
            present=True, confidence=0.9, raw_text="05-08-2027",
            day=5, month=8, year=2027, is_ambiguous=False,
        )
    )
    assert status_of(evaluate(fields, PACK_ID), "R6-1-d-date-legible") is FindingStatus.PASS


def test_a_genuinely_undecidable_date_is_flagged_as_advisory_only():
    fields = compliant(
        manufacture_date=PackDate(
            present=True, confidence=0.9, raw_text="05-08-2027",
            day=5, month=8, year=2027, is_ambiguous=True,
        )
    )
    f = finding(evaluate(fields, PACK_ID), "R6-1-d-date-legible")
    assert f.status is FindingStatus.FAIL
    assert f.severity is Severity.ADVISORY


# -- Rule 26 exemptions ------------------------------------------------------


def test_a_ten_gram_sachet_is_exempt_rather_than_non_compliant():
    """Suppressing false positives is as valuable as catching violations."""
    fields = compliant(
        net_quantity=NetQuantity(
            present=True, confidence=0.9, raw_text="8 g", value=8.0,
            unit="g", canonical_unit="g", value_in_base=8.0,
        ),
        mrp=Price(),
        consumer_care=ConsumerCare(),
    )
    report = evaluate(fields, PACK_ID)
    assert status_of(report, "R6-1-e-mrp") is FindingStatus.EXEMPT
    assert report.summary.failed == 0
    assert finding(report, "R6-1-e-mrp").exempted_by == "R26-small-pack"


def test_wholesale_packages_need_no_unit_sale_price():
    fields = compliant(unit_sale_price=Price())
    fields.package_type = PackageType.WHOLESALE
    report = evaluate(fields, PACK_ID)
    assert status_of(report, "R6-1-usp") is FindingStatus.EXEMPT


def test_a_retail_pack_missing_its_unit_sale_price_does_fail():
    report = evaluate(compliant(unit_sale_price=Price()), PACK_ID)
    assert status_of(report, "R6-1-usp") is FindingStatus.FAIL


# -- Applicability -----------------------------------------------------------


def test_country_of_origin_is_only_required_of_imported_goods():
    domestic = evaluate(compliant(), PACK_ID)
    assert status_of(domestic, "R6-country-of-origin") is FindingStatus.NOT_APPLICABLE

    imported = compliant(origin=Origin(present=False, is_imported=True))
    assert status_of(evaluate(imported, PACK_ID), "R6-country-of-origin") is FindingStatus.FAIL


def test_unknown_import_status_does_not_trigger_the_origin_rule():
    """We do not guess. If we cannot tell it is imported, the rule stays silent."""
    fields = compliant(origin=Origin(present=False, is_imported=None))
    assert status_of(evaluate(fields, PACK_ID), "R6-country-of-origin") is FindingStatus.NOT_APPLICABLE


def test_best_before_is_required_only_of_perishables():
    fields = compliant(best_before=PackDate())
    assert status_of(evaluate(fields, PACK_ID), "R6-best-before") is FindingStatus.NOT_APPLICABLE
    fields.is_perishable = True
    assert status_of(evaluate(fields, PACK_ID), "R6-best-before") is FindingStatus.FAIL


# -- Rule 9(1) language ------------------------------------------------------


def test_declarations_must_be_in_devanagari_or_english():
    fields = compliant()
    fields.ocr_scripts_seen = [Script.OTHER]
    assert status_of(evaluate(fields, PACK_ID), "R9-1-language") is FindingStatus.FAIL

    fields.ocr_scripts_seen = [Script.DEVANAGARI]
    assert status_of(evaluate(fields, PACK_ID), "R9-1-language") is FindingStatus.PASS


# -- Rule 9 contrast ---------------------------------------------------------


def test_low_contrast_declarations_fail_and_the_report_owns_the_proxy():
    fields = compliant(declaration_contrast_ratio=1.9)
    f = finding(evaluate(fields, PACK_ID), "R9-contrast")
    assert f.status is FindingStatus.FAIL
    # The rule says "conspicuously"; we must not pretend it states a number.
    assert "proxy" in f.explanation


# -- Rule 6(10A): the 2026 amendment -----------------------------------------


def test_platform_without_a_country_filter_fails_the_2026_amendment():
    fields = compliant(origin=Origin(present=True, country="Vietnam", is_imported=True))
    fields.scan_source = ScanSource.ECOMMERCE_LISTING
    fields.platform_has_country_filter = False
    fields.platform_country_filter_sortable = False
    f = finding(evaluate(fields, PACK_ID), "R6-10A-coo-filter")
    assert f.status is FindingStatus.FAIL
    assert f.severity is Severity.CRITICAL


def test_a_searchable_but_unsortable_filter_still_fails():
    """Since 01.07.2026 the rule requires both, not either."""
    fields = compliant(origin=Origin(present=True, country="Vietnam", is_imported=True))
    fields.scan_source = ScanSource.ECOMMERCE_LISTING
    fields.platform_has_country_filter = True
    fields.platform_country_filter_sortable = False
    f = finding(evaluate(fields, PACK_ID), "R6-10A-coo-filter")
    assert f.status is FindingStatus.FAIL
    assert "not sortable" in f.explanation


def test_the_filter_rule_does_not_apply_to_a_field_inspection():
    assert status_of(evaluate(compliant(), PACK_ID), "R6-10A-coo-filter") is FindingStatus.NOT_APPLICABLE


# -- Scoring -----------------------------------------------------------------


def test_undecidable_rules_do_not_drag_the_score_down():
    """A dim photograph must not make a compliant pack look non-compliant."""
    clear = evaluate(compliant(), PACK_ID)
    fields = compliant(scale=None)
    fields.min_letter_height = None
    murky = evaluate(fields, PACK_ID)

    assert murky.summary.indeterminate > clear.summary.indeterminate
    assert murky.summary.compliance_score == clear.summary.compliance_score == 100.0


def test_violations_are_ordered_by_severity():
    fields = compliant(mrp=Price())
    fields.net_quantity.unit = "gms."
    ordered = evaluate(fields, PACK_ID).violations()
    severities = [f.severity for f in ordered]
    assert severities == sorted(severities, key=lambda s: {"CRITICAL": 0, "MAJOR": 1, "ADVISORY": 2}[s])
