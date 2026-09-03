"""Score the pipeline against ground truth and publish the numbers.

    python ml/eval/report.py

Writes ``docs/accuracy.md``.

When a judge asks "how accurate is it?", the answer has to be a table, not an
adjective. This produces one.

**What this measures, and what it does not.** The corpus here is rendered, so
the ground truth is arithmetic rather than a calliper reading and every
millimetre figure is exact. That makes it the right instrument for the question
it answers -- given a clean image, is the geometry correct? -- and the wrong
instrument for the question that matters most, which is how the system behaves
on real packaging: foil, curvature, glare, motion blur, and typography designed
to be beautiful rather than legible. The golden set of photographed labels is
what settles that, and until it exists these numbers are a floor and not a
claim. The report says so on its face.
"""

from __future__ import annotations

import pathlib
import random
import statistics
import sys
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "eval"))

import synth  # noqa: E402

from astra_rules import RulePack, evaluate  # noqa: E402
from astra_schema import FindingStatus, PackageShape  # noqa: E402
from vision.pipeline.analyse import analyse  # noqa: E402

PACK_ID = "lmpc-2011@2026.07.01"

#: Declarations the extractor is expected to find on every rendered label.
EXPECTED_FIELDS = [
    "manufacturer",
    "common_name",
    "net_quantity",
    "mrp",
    "unit_sale_price",
    "manufacture_date",
    "consumer_care",
    "origin",
]


@dataclass
class Case:
    """One rendered label and what the engine made of it."""

    compliant_by_construction: bool
    with_card: bool
    dimensions_declared: bool
    truth_height_mm: float
    measured_height_mm: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    calibration: str = "NONE"
    fields_found: set[str] = field(default_factory=set)
    height_status: FindingStatus | None = None
    verdict: str = ""


def build_corpus(count: int, seed: int) -> list[tuple[bytes, dict, bool, bool, bool]]:
    """Render labels across the three calibration situations that occur.

    A card in frame, no card but dimensions declared (the e-commerce case, where
    a listing must carry them), and neither -- an inspector who photographed a
    shelf and moved on. The third arm is the one that shows what the engine does
    when it genuinely cannot measure, so it has to be represented.
    """
    rng = random.Random(seed)
    corpus = []
    for _ in range(count):
        offend = rng.random() < 0.5
        with_card = rng.random() < 0.60
        dimensions_declared = with_card or rng.random() < 0.55

        width_mm = rng.choice([70.0, 90.0, 110.0, 140.0])
        height_mm = rng.choice([120.0, 150.0, 180.0, 220.0])

        # Sizes are kept clear of the statutory threshold on both sides. A pack
        # printed at exactly the required height is genuinely undecidable, and
        # scoring the engine on coin-flips would flatter or damn it at random
        # rather than measure anything.
        net_qty_mm = rng.uniform(1.0, 1.8) if offend else rng.uniform(3.0, 4.5)

        png, truth = synth.render(
            synth.LabelSpec(
                width_mm=width_mm,
                height_mm=height_mm,
                declarations=synth.default_declarations(
                    net_qty_mm=net_qty_mm,
                    body_mm=rng.uniform(1.5, 2.2),
                ),
                with_id1_card=with_card,
            )
        )
        corpus.append((png, truth, not offend, with_card, dimensions_declared))
    return corpus


def run(count: int = 40, seed: int = 26034) -> list[Case]:
    cases: list[Case] = []
    corpus = build_corpus(count, seed)

    for index, (png, truth, compliant, with_card, declared) in enumerate(corpus, start=1):
        fields = analyse(
            png,
            shape=PackageShape.RECTANGULAR,
            height_mm=truth["package_height_mm"] if declared else None,
            width_mm=truth["package_width_mm"] if declared else None,
        )
        report = evaluate(fields, PACK_ID)

        case = Case(
            compliant_by_construction=compliant,
            with_card=with_card,
            dimensions_declared=declared,
            truth_height_mm=truth["net_quantity_height_mm"],
            calibration=str(fields.scale.source) if fields.scale else "NONE",
            fields_found={f for f in EXPECTED_FIELDS if getattr(fields, f).present},
            verdict=report.summary.verdict,
        )

        measured = [s.height for s in fields.net_quantity.spans if s.height]
        if measured:
            best = min(measured, key=lambda m: m.value_mm)
            case.measured_height_mm = best.value_mm
            case.ci_low, case.ci_high = best.ci_low_mm, best.ci_high_mm

        finding = next(
            (f for f in report.findings if f.rule_id == "R9-T1-netqty-height"), None
        )
        case.height_status = finding.status if finding else None

        cases.append(case)
        print(f"  {index}/{len(corpus)} scored", flush=True)

    return cases


def _pct(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.1f}%" if denominator else "—"


def render_markdown(cases: list[Case]) -> str:
    pack = RulePack.load(PACK_ID)

    # -- measurement ---------------------------------------------------------
    measured = [c for c in cases if c.measured_height_mm is not None]
    errors = [abs(c.measured_height_mm - c.truth_height_mm) for c in measured]
    covered = sum(
        1 for c in measured if c.ci_low <= c.truth_height_mm <= c.ci_high
    )

    # -- the height rule, scored only where a verdict was actually reached ----
    decided = [
        c
        for c in cases
        if c.height_status in (FindingStatus.PASS, FindingStatus.FAIL)
    ]
    tp = sum(
        1 for c in decided if not c.compliant_by_construction and c.height_status is FindingStatus.FAIL
    )
    fp = sum(
        1 for c in decided if c.compliant_by_construction and c.height_status is FindingStatus.FAIL
    )
    fn = sum(
        1 for c in decided if not c.compliant_by_construction and c.height_status is FindingStatus.PASS
    )
    tn = sum(
        1 for c in decided if c.compliant_by_construction and c.height_status is FindingStatus.PASS
    )
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    undecided = [c for c in cases if c.height_status is FindingStatus.INDETERMINATE]
    with_card = [c for c in cases if c.with_card]
    declared_only = [c for c in cases if not c.with_card and c.dimensions_declared]
    no_reference = [c for c in cases if not c.with_card and not c.dimensions_declared]

    lines: list[str] = []
    add = lines.append

    add("# Accuracy")
    add("")
    add(f"Generated by `python ml/eval/report.py` over {len(cases)} rendered labels,")
    add(f"judged under rule pack `{pack.identifier}`.")
    add("")
    add("> **What this is.** The corpus is rendered, so ground truth is arithmetic")
    add("> rather than a calliper reading and every millimetre below is exact. That")
    add("> makes this the right instrument for one question — given a clean image, is")
    add("> the geometry correct? — and the wrong one for the question that matters")
    add("> most: how the system behaves on real packaging, with foil, curvature,")
    add("> glare, and typography designed to be beautiful rather than legible. The")
    add("> golden set of photographed labels settles that. Until it exists, treat")
    add("> these as a floor, not a claim.")
    add("")

    add("## Measuring print height")
    add("")
    add("| Metric | Value |")
    add("| --- | --- |")
    add(f"| Labels where a numeral was measured | {len(measured)} of {len(cases)} |")
    add(f"| Mean absolute error | {statistics.mean(errors):.3f} mm |" if errors else "| Mean absolute error | — |")
    add(f"| Median absolute error | {statistics.median(errors):.3f} mm |" if errors else "| Median absolute error | — |")
    add(f"| Worst error | {max(errors):.3f} mm |" if errors else "| Worst error | — |")
    add(f"| True value inside the reported interval | {_pct(covered, len(measured))} |")
    add("")
    add("The last row is the one that matters. The reported interval is what the")
    add("engine refuses to convict outside of, so if the truth falls outside it the")
    add("interval is decoration and the whole `INDETERMINATE` gate is theatre.")
    add("")

    add("## Rule 9 Table-I — net quantity numeral height")
    add("")
    add(f"Scored over the {len(decided)} labels where a verdict was reached. The")
    add(f"{len(undecided)} left undecided are excluded rather than counted as")
    add("either outcome: declining to decide is the designed behaviour, not an error.")
    add("")
    add("| Metric | Value |")
    add("| --- | --- |")
    add(f"| Precision | {precision:.3f} |")
    add(f"| Recall | {recall:.3f} |")
    add(f"| F1 | {f1:.3f} |")
    add(f"| True positives | {tp} |")
    add(f"| False positives | {fp} |")
    add(f"| False negatives | {fn} |")
    add(f"| True negatives | {tn} |")
    add("")
    add("A false positive here is a manufacturer wrongly accused, so it is weighted")
    add("more heavily than a miss in every design decision upstream of this table.")
    add("")

    add("## What a reference object is worth")
    add("")
    add("| Frame | Labels | Height rule decided | Undecided | Mean error |")
    add("| --- | --- | --- | --- | --- |")
    arms = (
        ("ID-1 card in frame", with_card),
        ("No card, dimensions declared", declared_only),
        ("Neither", no_reference),
    )
    for label, group in arms:
        resolved = sum(
            1
            for c in group
            if c.height_status in (FindingStatus.PASS, FindingStatus.FAIL)
        )
        group_errors = [
            abs(c.measured_height_mm - c.truth_height_mm)
            for c in group
            if c.measured_height_mm is not None
        ]
        mean_error = f"{statistics.mean(group_errors):.3f} mm" if group_errors else "—"
        add(
            f"| {label} | {len(group)} | {_pct(resolved, len(group))} | "
            f"{_pct(len(group) - resolved, len(group))} | {mean_error} |"
        )
    add("")
    add("Two things follow, and the second is the one worth saying aloud.")
    add("")
    add("A declared width is a usable ruler. Where an e-commerce listing carries")
    add("the package dimensions — which it must — the height rules can be decided")
    add("without anyone holding a card up to a screen, though less precisely than")
    add("with one, and the reported interval widens to say so.")
    add("")
    add("With neither, the engine decides nothing at all. That is the design")
    add("working: no reference object means no ruler, and no ruler means no")
    add("accusation. The inspector is asked for a second photograph instead.")
    add("")

    add("## Extracting declarations")
    add("")
    add("| Declaration | Found |")
    add("| --- | --- |")
    for name in EXPECTED_FIELDS:
        found = sum(1 for c in cases if name in c.fields_found)
        add(f"| {name.replace('_', ' ')} | {_pct(found, len(cases))} |")
    add("")

    add("## Calibration sources used")
    add("")
    add("| Source | Labels |")
    add("| --- | --- |")
    sources: dict[str, int] = {}
    for case in cases:
        sources[case.calibration] = sources.get(case.calibration, 0) + 1
    for source, n in sorted(sources.items(), key=lambda kv: -kv[1]):
        add(f"| {source} | {n} |")
    add("")

    return "\n".join(lines) + "\n"


def main() -> None:
    print(f"Scoring the pipeline against {PACK_ID}…")
    cases = run()
    output = ROOT / "docs" / "accuracy.md"
    output.write_text(render_markdown(cases), encoding="utf-8")
    print(f"\nWrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
