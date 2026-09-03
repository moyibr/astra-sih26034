"""The check operators a rule pack can invoke.

Each operator is a small, total function from ``(fields, pack, params)`` to an
outcome. They are deliberately plain Python rather than an expression language
embedded in YAML: the law is data, but the *reasoning* about the law needs to be
readable, unit-testable and reviewable by someone who knows the rules and not
our DSL.

Every operator obeys three house rules:

* Never raise. A missing or malformed input yields ``INDETERMINATE``, never a
  crash and never a violation.
* Never assert a violation from an unmeasurable input. Absence of evidence is
  ``INDETERMINATE``; only positive evidence of non-compliance is ``FAIL``.
* Always explain. ``explanation`` is written to be pasted into a notice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

from astra_schema import (
    EvidenceRef,
    ExtractedFields,
    FieldEvidence,
    FindingStatus,
    Measurement,
    PackDate,
    Price,
    TextSpan,
)

from .pack import RulePack

# Characters Rule 9 itself excludes from the width-to-height requirement.
_WIDTH_RATIO_EXEMPT_CHARS = {"1", "i", "I", "l", ".", ",", ":", "-", "/", "|", "!"}

_CALIBRATION_HINT = (
    "Place any ID-card-sized card (Aadhaar, PAN or a debit card) flat beside the "
    "pack and re-shoot, so the millimetre scale can be recovered."
)


@dataclass
class CheckOutcome:
    status: FindingStatus
    measured: str | None = None
    required: str | None = None
    explanation: str = ""
    confidence: float = 1.0
    measurement: Measurement | None = None
    evidence: list[EvidenceRef] = dc_field(default_factory=list)


@dataclass
class CheckContext:
    fields: ExtractedFields
    pack: RulePack
    params: dict[str, Any]


CheckFn = Callable[[CheckContext], CheckOutcome]
CHECKS: dict[str, CheckFn] = {}


def check(op: str) -> Callable[[CheckFn], CheckFn]:
    def register(fn: CheckFn) -> CheckFn:
        CHECKS[op] = fn
        return fn

    return register


# -- helpers -----------------------------------------------------------------


def _evidence(fields: ExtractedFields, spans: list[TextSpan], caption: str) -> list[EvidenceRef]:
    return [
        EvidenceRef(
            image_sha256=fields.image_sha256,
            polygon=s.polygon,
            ocr_text=s.text,
            ocr_confidence=s.confidence,
            caption=caption,
        )
        for s in spans[:4]
    ]


def _get_field(fields: ExtractedFields, name: str) -> FieldEvidence | None:
    value = getattr(fields, name, None)
    return value if isinstance(value, FieldEvidence) else None


def _no_scale(fields: ExtractedFields) -> bool:
    return fields.scale is None or not fields.scale.is_usable_for_legal_assertion


# -- presence checks ---------------------------------------------------------


@check("field_declared")
def field_declared(ctx: CheckContext) -> CheckOutcome:
    name = ctx.params.get("field", "")
    minimum = float(ctx.params.get("min_confidence", 0.0))
    target = _get_field(ctx.fields, name)

    if target is None:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation=f"The pipeline produced no '{name}' field to assess.",
            confidence=0.0,
        )
    if target.present and target.confidence >= minimum:
        return CheckOutcome(
            FindingStatus.PASS,
            measured=target.raw_text,
            explanation=f"Declaration found: {target.raw_text!r}.",
            confidence=target.confidence,
            evidence=_evidence(ctx.fields, target.spans, name),
        )
    if target.present:
        # Something was read, but too faintly to accuse anyone over.
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            measured=target.raw_text,
            explanation=(
                f"A possible declaration was read as {target.raw_text!r} but only at "
                f"{target.confidence:.0%} confidence, below the {minimum:.0%} needed "
                "to rely on it. Manual verification required."
            ),
            confidence=target.confidence,
            evidence=_evidence(ctx.fields, target.spans, name),
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured="not found",
        required="present",
        explanation="No such declaration could be located anywhere on the package.",
        confidence=0.85,
    )


@check("all_declared")
def all_declared(ctx: CheckContext) -> CheckOutcome:
    names: list[str] = list(ctx.params.get("fields", []))
    missing = [n for n in names if not (getattr(ctx.fields, n, None) or FieldEvidence()).present]
    if not missing:
        return CheckOutcome(
            FindingStatus.PASS,
            explanation=f"All {len(names)} required declarations are present on the listing.",
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured=f"missing: {', '.join(missing)}",
        required=", ".join(names),
        explanation=(
            f"The listing omits {len(missing)} of {len(names)} mandatory declarations: "
            f"{', '.join(missing)}."
        ),
        confidence=0.85,
    )


@check("net_quantity_declared")
def net_quantity_declared(ctx: CheckContext) -> CheckOutcome:
    nq = ctx.fields.net_quantity
    if nq.declared_by_count and nq.value is not None:
        return CheckOutcome(
            FindingStatus.PASS,
            measured=f"{nq.value:g} (by number)",
            explanation="Net quantity is declared by number.",
            confidence=nq.confidence,
            evidence=_evidence(ctx.fields, nq.spans, "net quantity"),
        )
    if nq.present and nq.value is not None and nq.canonical_unit:
        return CheckOutcome(
            FindingStatus.PASS,
            measured=f"{nq.value:g} {nq.unit}",
            explanation=f"Net quantity declared as {nq.value:g} {nq.unit}.",
            confidence=nq.confidence,
            evidence=_evidence(ctx.fields, nq.spans, "net quantity"),
        )
    if nq.present:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            measured=nq.raw_text,
            explanation=(
                f"Text resembling a net quantity was read as {nq.raw_text!r} but no "
                "quantity and recognised unit could be parsed from it."
            ),
            confidence=nq.confidence,
            evidence=_evidence(ctx.fields, nq.spans, "net quantity"),
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured="not found",
        required="quantity with a standard unit, or a count",
        explanation="No net quantity declaration could be located on the package.",
        confidence=0.85,
    )


@check("unit_symbol_canonical")
def unit_symbol_canonical(ctx: CheckContext) -> CheckOutcome:
    nq = ctx.fields.net_quantity
    if not nq.unit:
        return CheckOutcome(
            FindingStatus.NOT_APPLICABLE,
            explanation="No unit was printed, so there is no symbol to assess.",
        )
    symbol, exact = ctx.pack.canonical_unit_for(nq.unit)
    if exact:
        return CheckOutcome(
            FindingStatus.PASS,
            measured=nq.unit,
            explanation=f"Unit printed as the correct SI symbol {symbol!r}.",
            confidence=nq.confidence,
            evidence=_evidence(ctx.fields, nq.spans, "unit symbol"),
        )
    if symbol:
        return CheckOutcome(
            FindingStatus.FAIL,
            measured=nq.unit,
            required=symbol,
            explanation=(
                f"The unit is printed as {nq.unit!r}. The SI symbol is {symbol!r} - "
                "symbols are not pluralised and take no full stop."
            ),
            confidence=nq.confidence,
            evidence=_evidence(ctx.fields, nq.spans, "unit symbol"),
        )
    return CheckOutcome(
        FindingStatus.INDETERMINATE,
        measured=nq.unit,
        explanation=f"The unit {nq.unit!r} was not recognised; it may be an OCR error.",
        confidence=0.3,
    )


# -- price checks ------------------------------------------------------------


@check("mrp_inclusive_phrase")
def mrp_inclusive_phrase(ctx: CheckContext) -> CheckOutcome:
    mrp: Price = ctx.fields.mrp
    if not mrp.present:
        return CheckOutcome(
            FindingStatus.NOT_APPLICABLE,
            explanation="No retail sale price was found, so its wording cannot be assessed.",
        )
    if mrp.has_inclusive_of_taxes_phrase:
        return CheckOutcome(
            FindingStatus.PASS,
            explanation="The price declaration carries the words 'inclusive of all taxes'.",
            confidence=mrp.confidence,
            evidence=_evidence(ctx.fields, mrp.spans, "retail sale price"),
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured=mrp.raw_text,
        required="... inclusive of all taxes",
        explanation=(
            "The retail sale price is declared without the words 'inclusive of all "
            "taxes', so a consumer cannot tell whether tax is extra."
        ),
        confidence=mrp.confidence,
        evidence=_evidence(ctx.fields, mrp.spans, "retail sale price"),
    )


@check("single_mrp")
def single_mrp(ctx: CheckContext) -> CheckOutcome:
    mrp: Price = ctx.fields.mrp
    distinct = sorted({round(a, 2) for a in mrp.candidate_amounts})
    if not mrp.present or len(distinct) <= 1:
        return CheckOutcome(
            FindingStatus.PASS,
            measured=f"{mrp.amount:g}" if mrp.amount is not None else None,
            explanation="A single maximum retail price is declared.",
            confidence=mrp.confidence,
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured=" / ".join(f"Rs {a:g}" for a in distinct),
        required="one price",
        explanation=(
            f"{len(distinct)} different maximum retail prices were found on the same "
            f"pack ({', '.join(f'Rs {a:g}' for a in distinct)}). A pack may carry only one."
        ),
        confidence=min(0.9, mrp.confidence),
        evidence=_evidence(ctx.fields, mrp.spans, "conflicting prices"),
    )


# -- date checks -------------------------------------------------------------


@check("date_declared")
def date_declared(ctx: CheckContext) -> CheckOutcome:
    name = ctx.params.get("field", "manufacture_date")
    d = getattr(ctx.fields, name, None)
    if not isinstance(d, PackDate):
        return CheckOutcome(FindingStatus.INDETERMINATE, explanation=f"No '{name}' field.")
    if d.present and d.month and d.year:
        return CheckOutcome(
            FindingStatus.PASS,
            measured=f"{d.month:02d}/{d.year}",
            explanation=f"Date declared as {d.month:02d}/{d.year}.",
            confidence=d.confidence,
            evidence=_evidence(ctx.fields, d.spans, name),
        )
    if d.present:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            measured=d.raw_text,
            explanation=(
                f"Date-like text {d.raw_text!r} was read but a month and year could "
                "not be resolved from it."
            ),
            confidence=d.confidence,
            evidence=_evidence(ctx.fields, d.spans, name),
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured="not found",
        required="month and year",
        explanation="No such date declaration could be located on the package.",
        confidence=0.8,
    )


@check("date_unambiguous")
def date_unambiguous(ctx: CheckContext) -> CheckOutcome:
    name = ctx.params.get("field", "manufacture_date")
    d = getattr(ctx.fields, name, None)
    if not isinstance(d, PackDate) or not d.present:
        return CheckOutcome(
            FindingStatus.NOT_APPLICABLE,
            explanation="No date was found, so its format cannot be assessed.",
        )
    if not d.is_ambiguous:
        return CheckOutcome(
            FindingStatus.PASS,
            measured=d.raw_text,
            explanation="The date can be read only one way.",
            confidence=d.confidence,
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured=d.raw_text,
        required="month in words, or MM/YYYY",
        explanation=(
            f"{d.raw_text!r} is genuinely ambiguous: both components are 12 or less "
            "and no month name is given, so a consumer cannot tell which is the month."
        ),
        confidence=0.7,
        evidence=_evidence(ctx.fields, d.spans, name),
    )


# -- consumer care -----------------------------------------------------------


@check("consumer_care_complete")
def consumer_care_complete(ctx: CheckContext) -> CheckOutcome:
    cc = ctx.fields.consumer_care
    if not cc.present:
        return CheckOutcome(
            FindingStatus.FAIL,
            measured="not found",
            required="name, address and a contact channel",
            explanation="No consumer care details could be located on the package.",
            confidence=0.85,
        )

    missing: list[str] = []
    if ctx.params.get("require_name", True) and not cc.contact_name:
        missing.append("name or designation of the person to be contacted")
    if ctx.params.get("require_address", True) and not cc.address:
        missing.append("complete postal address")

    one_of: list[str] = list(ctx.params.get("require_one_of", ["phone", "email"]))
    if one_of and not any(getattr(cc, channel, None) for channel in one_of):
        missing.append(" or ".join(one_of))

    present = [n for n in ("contact_name", "address", "phone", "email") if getattr(cc, n, None)]
    if not missing:
        return CheckOutcome(
            FindingStatus.PASS,
            measured=", ".join(present),
            explanation=f"Consumer care details are complete ({', '.join(present)}).",
            confidence=cc.confidence,
            evidence=_evidence(ctx.fields, cc.spans, "consumer care"),
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured=f"present: {', '.join(present) or 'none'}",
        required="name, complete address, and a telephone number or e-mail",
        explanation=(
            "The consumer care declaration is incomplete. Missing: "
            + "; ".join(missing)
            + ". A consumer cannot pursue a grievance on what is printed."
        ),
        confidence=cc.confidence or 0.7,
        evidence=_evidence(ctx.fields, cc.spans, "consumer care"),
    )


# -- legibility --------------------------------------------------------------


@check("language_permitted")
def language_permitted(ctx: CheckContext) -> CheckOutcome:
    allowed = {str(s) for s in ctx.params.get("allowed", ["LATIN", "DEVANAGARI"])}
    seen = {str(s) for s in ctx.fields.ocr_scripts_seen}
    if not seen:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation="No text was recognised, so the language cannot be assessed.",
            confidence=0.0,
        )
    if seen & allowed:
        return CheckOutcome(
            FindingStatus.PASS,
            measured=", ".join(sorted(seen)),
            explanation=f"Declarations appear in a permitted script ({', '.join(sorted(seen & allowed))}).",
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured=", ".join(sorted(seen)),
        required=" or ".join(sorted(allowed)),
        explanation=(
            "The declarations do not appear in Hindi (Devanagari script) or in English."
        ),
        confidence=0.6,
    )


def _min_numeral_measurement(field_obj: FieldEvidence) -> tuple[Measurement | None, TextSpan | None]:
    best: tuple[Measurement | None, TextSpan | None] = (None, None)
    for span in field_obj.numeral_spans:
        if span.height is None:
            continue
        if best[0] is None or span.height.value_mm < best[0].value_mm:
            best = (span.height, span)
    return best


@check("numeral_height_gte")
def numeral_height_gte(ctx: CheckContext) -> CheckOutcome:
    fields = ctx.fields
    table_name = ctx.params.get("table", "table_I")
    table = ctx.pack.tables.get(table_name)
    if table is None:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation=f"Rule pack has no table {table_name!r}.",
        )

    if _no_scale(fields):
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation=(
                "No trustworthy millimetre scale was recovered from this image, so "
                "glyph height cannot be asserted. " + _CALIBRATION_HINT
            ),
            confidence=0.0,
        )

    area = fields.geometry.pdp_area_cm2 or fields.geometry.compute_pdp_area_cm2()
    if area is None:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation=(
                "The area of the principal display panel could not be determined, and "
                "the required glyph height depends entirely on it. Record the package "
                "shape and dimensions to complete this check."
            ),
            confidence=0.0,
        )

    target = _get_field(fields, ctx.params.get("field", "net_quantity"))
    if target is None or not target.present:
        return CheckOutcome(
            FindingStatus.NOT_APPLICABLE,
            explanation="The declaration itself is absent; its height is moot.",
        )

    measurement, span = _min_numeral_measurement(target)
    if measurement is None:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation="No numeral in the declaration could be measured.",
            confidence=0.0,
        )

    required, band = table.threshold_for(area, fields.geometry.print_method)
    status = measurement.at_least(required)

    band_label = f"<= {band.upto:g} cm2" if band.upto is not None else "above 2500 cm2"
    detail = (
        f"Principal display panel measures {area:.0f} cm2 ({band_label} band), so "
        f"{table_name.replace('_', '-')} requires numerals of at least {required:g} mm. "
        f"The smallest numeral measures {measurement}."
    )
    if status is FindingStatus.INDETERMINATE:
        detail += (
            " The measurement interval spans the threshold, so no violation is asserted."
        )

    return CheckOutcome(
        status=status,
        measured=str(measurement),
        required=f"{required:g} mm",
        explanation=detail,
        confidence=0.9 if status is not FindingStatus.INDETERMINATE else 0.4,
        measurement=measurement,
        evidence=_evidence(fields, [span] if span else [], "smallest numeral"),
    )


@check("letter_height_gte")
def letter_height_gte(ctx: CheckContext) -> CheckOutcome:
    fields = ctx.fields
    if _no_scale(fields):
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation="No trustworthy millimetre scale. " + _CALIBRATION_HINT,
            confidence=0.0,
        )
    measurement = fields.min_letter_height
    if measurement is None:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation="No letter height was measured on this package.",
            confidence=0.0,
        )

    from astra_schema import PrintMethod

    required = float(
        ctx.params.get("embossed_mm", 2.0)
        if fields.geometry.print_method is PrintMethod.EMBOSSED
        else ctx.params.get("printed_mm", 1.0)
    )
    status = measurement.at_least(required)
    return CheckOutcome(
        status=status,
        measured=str(measurement),
        required=f"{required:g} mm",
        explanation=(
            f"The smallest letter in the mandatory declarations measures {measurement}; "
            f"the rule requires at least {required:g} mm."
        ),
        confidence=0.9 if status is not FindingStatus.INDETERMINATE else 0.4,
        measurement=measurement,
    )


@check("width_ratio_gte")
def width_ratio_gte(ctx: CheckContext) -> CheckOutcome:
    """Width against height is a pure ratio, so it needs no millimetre scale.

    It does assume the image has been rectified, since perspective would squash
    glyphs horizontally and manufacture a violation out of nothing.
    """
    required = float(ctx.params.get("ratio", 1 / 3))
    worst: tuple[float, TextSpan] | None = None

    for name in ("net_quantity", "mrp", "manufacture_date", "consumer_care"):
        target = _get_field(ctx.fields, name)
        if target is None:
            continue
        for span in target.spans:
            if not span.ink_height_px or not span.ink_width_px:
                continue
            core = [c for c in span.text if c not in _WIDTH_RATIO_EXEMPT_CHARS and not c.isspace()]
            if not core:
                continue
            # ink_width_px is already the *mean width of one glyph*, not the
            # width of the whole span, so it compares directly against the glyph
            # height. Dividing it by the character count as well collapses every
            # ratio towards zero and reports condensed type on every label.
            ratio = span.ink_width_px / span.ink_height_px
            if worst is None or ratio < worst[0]:
                worst = (ratio, span)

    if worst is None:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation="No glyph had both width and height measured.",
            confidence=0.0,
        )

    ratio, span = worst
    if ratio >= required:
        return CheckOutcome(
            FindingStatus.PASS,
            measured=f"{ratio:.2f}",
            required=f"{required:.2f}",
            explanation=f"Narrowest characters are {ratio:.2f} times as wide as tall.",
            confidence=0.6,
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured=f"{ratio:.2f}",
        required=f"{required:.2f}",
        explanation=(
            f"Characters in {span.text!r} are only {ratio:.2f} times as wide as they are "
            f"tall; the rule requires at least {required:.2f} (one third)."
        ),
        confidence=0.6,
        evidence=_evidence(ctx.fields, [span], "condensed type"),
    )


@check("contrast_ratio_gte")
def contrast_ratio_gte(ctx: CheckContext) -> CheckOutcome:
    minimum = float(ctx.params.get("min_ratio", 4.5))
    ratio = ctx.fields.declaration_contrast_ratio
    if ratio is None:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation="Contrast between the declaration and its background was not measured.",
            confidence=0.0,
        )
    if ratio >= minimum:
        return CheckOutcome(
            FindingStatus.PASS,
            measured=f"{ratio:.1f}:1",
            required=f"{minimum:.1f}:1",
            explanation=f"Declarations contrast against their background at {ratio:.1f}:1.",
            confidence=0.75,
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured=f"{ratio:.1f}:1",
        required=f"{minimum:.1f}:1",
        explanation=(
            f"Declarations contrast against their background at only {ratio:.1f}:1. "
            f"The rule requires a conspicuously contrasting colour; we apply a "
            f"published WCAG threshold of {minimum:.1f}:1 as the working standard, "
            "which is a proxy and not a figure stated in the rule itself."
        ),
        confidence=0.7,
    )


# -- schedule and platform ---------------------------------------------------


@check("scheduled_pack_size")
def scheduled_pack_size(ctx: CheckContext) -> CheckOutcome:
    fields = ctx.fields
    nq = fields.net_quantity
    allowed = fields.scheduled_sizes_base
    if not allowed:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation="No prescribed sizes are loaded for this commodity.",
            confidence=0.0,
        )
    if nq.value_in_base is None:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation="Net quantity could not be converted to a base unit for comparison.",
            confidence=0.0,
        )
    if any(abs(nq.value_in_base - a) < 1e-6 for a in allowed):
        return CheckOutcome(
            FindingStatus.PASS,
            measured=f"{nq.value_in_base:g}",
            explanation="The pack size is one of those prescribed for this commodity.",
            confidence=0.8,
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured=f"{nq.value_in_base:g}",
        required=", ".join(f"{a:g}" for a in sorted(allowed)),
        explanation=(
            f"This is a scheduled commodity, which may be packed only in prescribed "
            f"quantities. {nq.value_in_base:g} is not among them."
        ),
        confidence=0.8,
        evidence=_evidence(fields, nq.spans, "net quantity"),
    )


@check("platform_country_filter")
def platform_country_filter(ctx: CheckContext) -> CheckOutcome:
    has = ctx.fields.platform_has_country_filter
    sortable = ctx.fields.platform_country_filter_sortable
    if has is None:
        return CheckOutcome(
            FindingStatus.INDETERMINATE,
            explanation="The platform's listing pages were not audited for a country-of-origin filter.",
            confidence=0.0,
        )
    if has and sortable:
        return CheckOutcome(
            FindingStatus.PASS,
            measured="searchable and sortable",
            explanation="The platform exposes a country-of-origin filter that is both searchable and sortable.",
            confidence=0.8,
        )
    if has and not sortable:
        return CheckOutcome(
            FindingStatus.FAIL,
            measured="searchable only",
            required="searchable and sortable",
            explanation=(
                "A country-of-origin filter exists but is not sortable. Since 01.07.2026 "
                "the rule requires both, so that a consumer can order imported products "
                "by origin and not merely find them."
            ),
            confidence=0.75,
        )
    return CheckOutcome(
        FindingStatus.FAIL,
        measured="absent",
        required="searchable and sortable",
        explanation=(
            "The platform sells imported products but offers no country-of-origin filter "
            "on its listing pages, as required since 01.07.2026."
        ),
        confidence=0.8,
    )
