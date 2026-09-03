"""Run the five field scenarios through the rule engine and print the reports.

This is the script to run in front of judges before the camera demo exists, and
the one to keep running afterwards: it shows the engine's reasoning in text,
including the two cases where it deliberately declines to accuse anyone.

    python scripts/demo_scenarios.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages" / "rulepacks" / "tests"))

from label_fixtures import PACK_ID, barcode_scale, compliant, good_scale, span  # noqa: E402

from astra_rules import evaluate  # noqa: E402
from astra_schema import (  # noqa: E402
    ConsumerCare,
    FindingStatus,
    Measurement,
    Origin,
    PackDate,
    Report,
    ScanSource,
    Severity,
)

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
RED, YELLOW, GREEN, BLUE, GREY = (
    "\033[31m", "\033[33m", "\033[32m", "\033[36m", "\033[90m",
)

STATUS_STYLE = {
    FindingStatus.FAIL: (RED, "VIOLATION"),
    FindingStatus.PASS: (GREEN, "compliant"),
    FindingStatus.INDETERMINATE: (YELLOW, "UNDECIDED"),
    FindingStatus.EXEMPT: (BLUE, "exempt"),
    FindingStatus.NOT_APPLICABLE: (GREY, "n/a"),
}
VERDICT_STYLE = {
    "COMPLIANT": GREEN,
    "PARTIALLY_COMPLIANT": YELLOW,
    "NEEDS_REVIEW": YELLOW,
    "NON_COMPLIANT": RED,
}


def wrap(text: str, width: int, indent: str) -> str:
    words, lines, current = text.split(), [], ""
    for w in words:
        if len(current) + len(w) + 1 > width:
            lines.append(current)
            current = w
        else:
            current = f"{current} {w}".strip()
    if current:
        lines.append(current)
    return f"\n{indent}".join(lines)


def show(title: str, subtitle: str, report: Report, *, only_interesting: bool = True) -> None:
    print(f"\n{BOLD}{'=' * 78}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{DIM}{subtitle}{RESET}")
    print(f"{BOLD}{'=' * 78}{RESET}")

    s = report.summary
    colour = VERDICT_STYLE[s.verdict]
    print(
        f"  {colour}{BOLD}{s.verdict}{RESET}   score {s.compliance_score:g}/100   "
        f"{DIM}pack {report.rulepack}{RESET}"
    )
    print(
        f"  {DIM}{s.passed} passed  {s.failed} failed  {s.indeterminate} undecided  "
        f"{s.exempt} exempt  {s.not_applicable} n/a{RESET}\n"
    )

    for f in report.findings:
        if only_interesting and f.status in (FindingStatus.PASS, FindingStatus.NOT_APPLICABLE):
            continue
        colour, label = STATUS_STYLE[f.status]
        sev = f" [{f.severity}]" if f.status is FindingStatus.FAIL else ""
        print(f"  {colour}{label:>10}{RESET}{sev}  {BOLD}{f.title}{RESET}")
        print(f"              {DIM}{f.citation}{RESET}")
        if f.measured or f.required:
            print(f"              found: {f.measured or '-'}   required: {f.required or '-'}")
        print(f"              {wrap(f.explanation, 62, ' ' * 14)}")
        print()

    if report.calibration_note:
        print(f"  {YELLOW}! {wrap(report.calibration_note, 70, '    ')}{RESET}\n")


def scenario_1_unit_symbol():
    f = compliant()
    f.net_quantity.unit = "gms."
    f.net_quantity.raw_text = "Net Weight: 100 gms."
    show(
        "1. The unit-symbol scam  -  'Net Weight: 100 gms.'",
        "Real, but minor. Ranked ADVISORY so it never buries a missing MRP.",
        evaluate(f, PACK_ID),
    )


def scenario_2_font_height():
    scale = good_scale()
    f = compliant(scale=scale)
    f.net_quantity.spans = [span("50 g", height_px=12, scale=scale)]
    f.min_letter_height = Measurement.from_pixels(11, scale)
    show(
        "2a. Hidden small print  -  measured against an ID-1 card",
        "Panel area decides the threshold, NOT net weight. 198 cm2 needs 2.5 mm.",
        evaluate(f, PACK_ID),
    )

    scale = barcode_scale()
    g = compliant(scale=scale)
    g.net_quantity.spans = [span("50 g", height_px=12, scale=scale)]
    g.min_letter_height = Measurement.from_pixels(11, scale)
    show(
        "2b. The same photograph, calibrated off the barcode instead",
        "EAN-13 permits 80%-200% magnification, so this ruler cannot convict.",
        evaluate(g, PACK_ID),
    )


def scenario_3_dual_mrp():
    f = compliant()
    f.mrp.candidate_amounts = [40.0, 60.0]
    f.mrp.raw_text = "MRP Rs 40 ... MRP Rs 60"
    f.scan_source = ScanSource.ECOMMERCE_LISTING
    f.origin = Origin(present=True, confidence=0.9, raw_text="India",
                      country="India", is_imported=False)
    show(
        "3. Dual MRP  -  Rs 40 in the shop, Rs 60 on the listing",
        "Two maximum retail prices on one pack.",
        evaluate(f, PACK_ID),
    )


def scenario_4_consumer_care():
    f = compliant(
        consumer_care=ConsumerCare(
            present=True, confidence=0.8,
            raw_text="For complaints, contact manager at feedback@email.example",
            email="feedback@email.example",
        )
    )
    show(
        "4. Consumer care hidden behind an e-mail alone",
        "An e-mail address is not a name, and it is not a postal address.",
        evaluate(f, PACK_ID),
    )


def scenario_5_dates():
    lawful = compliant(
        manufacture_date=PackDate(present=True, confidence=0.9, raw_text="05-08-2027",
                                  day=5, month=8, year=2027, is_ambiguous=False)
    )
    show(
        "5a. 'Best Before: 05-08-2027'  -  parsed unambiguously",
        "DD-MM-YYYY is lawful and ubiquitous in India. Flagging it would drown "
        "the officer in false positives, so we do not.",
        evaluate(lawful, PACK_ID),
    )

    murky = compliant(
        manufacture_date=PackDate(present=True, confidence=0.9, raw_text="05-08-2027",
                                  day=5, month=8, year=2027, is_ambiguous=True)
    )
    show(
        "5b. The same string when nothing else on the pack disambiguates it",
        "Only now does it become a finding - and only an advisory one.",
        evaluate(murky, PACK_ID),
    )


def scenario_6_amendment_2026():
    f = compliant(origin=Origin(present=True, confidence=0.9, raw_text="Vietnam",
                                country="Vietnam", is_imported=True))
    f.scan_source = ScanSource.ECOMMERCE_LISTING
    f.platform_has_country_filter = True
    f.platform_country_filter_sortable = False
    show(
        "6. Rule 6(10A)  -  country-of-origin filter, in force since 01.07.2026",
        "Architecture-level compliance: declaring the country is no longer enough "
        "if a consumer cannot sort by it.",
        evaluate(f, PACK_ID),
    )


def scenario_7_exemption():
    f = compliant()
    f.net_quantity.value = 8.0
    f.net_quantity.value_in_base = 8.0
    f.net_quantity.raw_text = "8 g"
    f.mrp.present = False
    f.consumer_care = ConsumerCare()
    show(
        "7. An 8 g shampoo sachet with no MRP  -  exempt, not guilty",
        "Suppressing false positives is worth as much as catching violations.",
        evaluate(f, PACK_ID),
    )


def main() -> None:
    print(f"\n{BOLD}ASTRA  -  Legal Metrology compliance engine{RESET}")
    print(f"{DIM}SIH26034  |  deterministic rule engine, no image required{RESET}")
    for fn in (
        scenario_1_unit_symbol,
        scenario_2_font_height,
        scenario_3_dual_mrp,
        scenario_4_consumer_care,
        scenario_5_dates,
        scenario_6_amendment_2026,
        scenario_7_exemption,
    ):
        fn()


if __name__ == "__main__":
    main()
