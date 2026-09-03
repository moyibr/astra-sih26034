"""What the rule engine produces, and what an officer ultimately signs.

A Finding is written to be readable by three different audiences without
translation: the inspector on a phone, the dashboard that aggregates thousands
of them, and the adjudicating officer who has to justify a notice.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .enums import FindingStatus, Severity
from .measurement import Measurement

Point = tuple[float, float]


class EvidenceRef(BaseModel):
    """A pointer back into the original image, so nothing is asserted blind."""

    image_sha256: str
    polygon: list[Point] = Field(default_factory=list)
    crop_uri: str | None = None
    ocr_text: str | None = None
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    caption: str | None = None


class Finding(BaseModel):
    """The verdict on exactly one rule for exactly one package."""

    rule_id: str
    citation: str
    """Statutory reference as it will be printed on a notice, e.g.
    'Rule 9, Table-I -- height of numerals'."""
    title: str
    status: FindingStatus
    severity: Severity

    measured: str | None = None
    required: str | None = None
    measurement: Measurement | None = None

    confidence: float = Field(default=1.0, ge=0, le=1)
    explanation: str = ""
    remedy: str | None = None
    exempted_by: str | None = None

    evidence: list[EvidenceRef] = Field(default_factory=list)

    @property
    def is_violation(self) -> bool:
        return self.status is FindingStatus.FAIL


class ReportSummary(BaseModel):
    total_rules: int = 0
    passed: int = 0
    failed: int = 0
    indeterminate: int = 0
    exempt: int = 0
    not_applicable: int = 0

    critical_violations: int = 0
    major_violations: int = 0
    advisory_violations: int = 0

    compliance_score: float = Field(default=0.0, ge=0, le=100)
    """Share of *decidable, applicable* rules that passed. Indeterminate and
    exempt rules are excluded from both sides of the fraction so that a badly
    lit photograph cannot make a compliant pack look non-compliant."""

    @property
    def verdict(self) -> str:
        if self.critical_violations:
            return "NON_COMPLIANT"
        if self.major_violations or self.advisory_violations:
            return "PARTIALLY_COMPLIANT"
        if self.indeterminate:
            return "NEEDS_REVIEW"
        return "COMPLIANT"


class Report(BaseModel):
    """The complete, self-contained record of one compliance assessment.

    A Report is reproducible: it names the rule pack that judged it, so re-running
    an old scan against the pack that was in force at the time yields the same
    verdict even after the law has moved on.
    """

    scan_id: str
    image_sha256: str
    rulepack: str
    """Pinned identifier, e.g. 'lmpc-2011@2026.07.01'."""
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    engine_version: str = "0.1.0"

    findings: list[Finding] = Field(default_factory=list)
    summary: ReportSummary = Field(default_factory=ReportSummary)

    calibration_note: str | None = None
    """Set when measurements were unusable, telling the inspector exactly what
    to do differently -- e.g. 'Place any ID-card-sized card beside the pack.'"""

    def violations(self) -> list[Finding]:
        order = {Severity.CRITICAL: 0, Severity.MAJOR: 1, Severity.ADVISORY: 2}
        return sorted(
            (f for f in self.findings if f.is_violation),
            key=lambda f: order[f.severity],
        )
