"""The deterministic core: extracted fields in, a defensible report out.

Nothing probabilistic happens here. The engine never sees an image and never
calls a model, so any report it produces can be replayed from stored fields and
will come back identical. That property is what lets an officer stand behind a
finding, and it is why the LLM in the pipeline upstream is confined to tidying
text rather than deciding anything.

Evaluation order matters and is deliberate:

1. Exemptions first, so a carve-out can never be reported as a violation.
2. Applicability, so rules about imported goods stay silent on domestic ones.
3. Prerequisites, so we do not complain about the wording of a price we never
   found.
4. The check itself.
"""

from __future__ import annotations

from typing import Any

from astra_schema import (
    ExtractedFields,
    Finding,
    FindingStatus,
    Report,
    ReportSummary,
    Severity,
)

from .checks import CHECKS, CheckContext, CheckOutcome
from .pack import ExemptionSpec, RulePack, RuleSpec

ENGINE_VERSION = "0.1.0"


# -- predicates --------------------------------------------------------------


def _predicate_value(fields: ExtractedFields, key: str) -> Any:
    """Resolve one supported predicate key against the extracted fields.

    The vocabulary is closed on purpose. A rule pack is authored by a legal
    workstream, not a programmer, and an arbitrary expression language in YAML
    would be both a code-injection surface and impossible to review.
    """
    match key:
        case "package_type":
            return str(fields.package_type)
        case "scan_source":
            return str(fields.scan_source)
        case "commodity_category":
            return (fields.commodity_category or "").lower()
        case "is_perishable":
            return fields.is_perishable
        case "commodity_is_scheduled":
            return fields.commodity_is_scheduled
        case "origin_is_imported":
            return fields.origin.is_imported
        case "net_quantity_by_count":
            return fields.net_quantity.declared_by_count
        case "net_quantity_base_lte":
            return fields.net_quantity.value_in_base
        case _:
            raise KeyError(f"unsupported predicate {key!r} in rule pack")


def matches(fields: ExtractedFields, predicate: dict[str, Any]) -> bool:
    """Every clause must hold (logical AND).

    An unknown value never satisfies a clause. If we cannot tell whether a pack
    is imported, a rule that only bites on imported packs simply does not apply,
    rather than firing on a guess.
    """
    for key, expected in predicate.items():
        if key.endswith("_lte"):
            actual = _predicate_value(fields, key)
            if actual is None or actual > float(expected):
                return False
            continue
        if key.endswith("_gte"):
            actual = _predicate_value(fields, key)
            if actual is None or actual < float(expected):
                return False
            continue

        actual = _predicate_value(fields, key)
        if isinstance(expected, str):
            if str(actual).lower() != expected.lower():
                return False
        elif actual != expected:
            return False
    return True


def active_exemptions(fields: ExtractedFields, pack: RulePack) -> list[ExemptionSpec]:
    return [e for e in pack.exemptions if matches(fields, e.when)]


# -- evaluation --------------------------------------------------------------


def _finding_from(rule: RuleSpec, outcome: CheckOutcome) -> Finding:
    return Finding(
        rule_id=rule.id,
        citation=rule.citation,
        title=rule.title,
        status=outcome.status,
        severity=rule.severity,
        measured=outcome.measured,
        required=outcome.required,
        measurement=outcome.measurement,
        confidence=outcome.confidence,
        explanation=outcome.explanation,
        remedy=rule.remedy if outcome.status is FindingStatus.FAIL else None,
        evidence=outcome.evidence,
    )


def evaluate(fields: ExtractedFields, pack: RulePack | str) -> Report:
    """Evaluate every rule in the pack against one package."""
    if isinstance(pack, str):
        pack = RulePack.load(pack)

    exemptions = active_exemptions(fields, pack)
    findings: list[Finding] = []
    status_by_id: dict[str, FindingStatus] = {}

    for rule in pack.rules:
        exemption = next((e for e in exemptions if e.covers(rule.id)), None)
        if exemption is not None:
            findings.append(
                Finding(
                    rule_id=rule.id,
                    citation=rule.citation,
                    title=rule.title,
                    status=FindingStatus.EXEMPT,
                    severity=rule.severity,
                    explanation=f"{exemption.reason} ({exemption.citation})",
                    exempted_by=exemption.id,
                )
            )
            status_by_id[rule.id] = FindingStatus.EXEMPT
            continue

        if rule.applies_when and not matches(fields, rule.applies_when):
            findings.append(
                Finding(
                    rule_id=rule.id,
                    citation=rule.citation,
                    title=rule.title,
                    status=FindingStatus.NOT_APPLICABLE,
                    severity=rule.severity,
                    explanation="This rule does not apply to a package of this kind.",
                )
            )
            status_by_id[rule.id] = FindingStatus.NOT_APPLICABLE
            continue

        unmet = [
            dep
            for dep in rule.requires
            if status_by_id.get(dep) not in (FindingStatus.PASS, None)
        ]
        if unmet:
            findings.append(
                Finding(
                    rule_id=rule.id,
                    citation=rule.citation,
                    title=rule.title,
                    status=FindingStatus.NOT_APPLICABLE,
                    severity=rule.severity,
                    explanation=(
                        "Not assessed because a declaration it depends on was not "
                        f"established ({', '.join(unmet)}). Reporting it as well would "
                        "double-count a single underlying defect."
                    ),
                )
            )
            status_by_id[rule.id] = FindingStatus.NOT_APPLICABLE
            continue

        fn = CHECKS.get(rule.check.op)
        if fn is None:
            findings.append(
                Finding(
                    rule_id=rule.id,
                    citation=rule.citation,
                    title=rule.title,
                    status=FindingStatus.INDETERMINATE,
                    severity=rule.severity,
                    confidence=0.0,
                    explanation=f"No implementation registered for check {rule.check.op!r}.",
                )
            )
            status_by_id[rule.id] = FindingStatus.INDETERMINATE
            continue

        outcome = fn(CheckContext(fields=fields, pack=pack, params=rule.check.params()))
        findings.append(_finding_from(rule, outcome))
        status_by_id[rule.id] = outcome.status

    report = Report(
        scan_id=fields.scan_id,
        image_sha256=fields.image_sha256,
        rulepack=pack.identifier,
        engine_version=ENGINE_VERSION,
        findings=findings,
        summary=summarise(findings),
    )

    if fields.scale is None or not fields.scale.is_usable_for_legal_assertion:
        blocked = sum(
            1
            for f in findings
            if f.status is FindingStatus.INDETERMINATE
            and (pack.rule(f.rule_id).requires_calibration if pack.rule(f.rule_id) else False)
        )
        if blocked:
            report.calibration_note = (
                f"{blocked} measurement-based rule(s) could not be decided because no "
                "trustworthy millimetre scale was available. Place any wallet-sized "
                "card flat beside the pack and re-shoot. Every other rule was "
                "assessed normally."
            )

    return report


def summarise(findings: list[Finding]) -> ReportSummary:
    s = ReportSummary(total_rules=len(findings))
    for f in findings:
        match f.status:
            case FindingStatus.PASS:
                s.passed += 1
            case FindingStatus.FAIL:
                s.failed += 1
            case FindingStatus.INDETERMINATE:
                s.indeterminate += 1
            case FindingStatus.EXEMPT:
                s.exempt += 1
            case FindingStatus.NOT_APPLICABLE:
                s.not_applicable += 1

        if f.status is FindingStatus.FAIL:
            match f.severity:
                case Severity.CRITICAL:
                    s.critical_violations += 1
                case Severity.MAJOR:
                    s.major_violations += 1
                case Severity.ADVISORY:
                    s.advisory_violations += 1

    # Only decidable, applicable rules count. A dim photograph must not be able
    # to drag a compliant pack's score down.
    decidable = s.passed + s.failed
    s.compliance_score = round(100.0 * s.passed / decidable, 1) if decidable else 100.0
    return s
