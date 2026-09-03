"""Physical measurements that carry their own uncertainty.

The whole legal defensibility of ASTRA rests on this module. A font-height
figure extracted from a photograph is an *estimate*, and how good that estimate
is depends entirely on what real-world object was used to convert pixels into
millimetres. We therefore refuse to move a bare float around the system: every
millimetre value travels with the interval it is trusted within and the name of
the reference object it came from.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .enums import CalibrationSource, FindingStatus

#: Relative uncertainty (1 = 100%) typically achievable from each reference.
#: Sources: ISO/IEC 7810 ID-1 cards are dimensionally tight; EAN-13 permits
#: 80%-200% magnification, so assuming 100% can be wrong by well over a factor
#: of two -- hence the deliberately punitive figure.
CALIBRATION_UNCERTAINTY: dict[CalibrationSource, float] = {
    CalibrationSource.ARUCO: 0.010,
    CalibrationSource.ID1_CARD: 0.020,
    CalibrationSource.MANUAL: 0.030,
    CalibrationSource.DECLARED_DIMENSION: 0.050,
    CalibrationSource.BARCODE_ASSUMED: 0.250,
    CalibrationSource.NONE: 1.000,
}

#: Above this relative uncertainty we will not assert a millimetre-based
#: violation at all; the rule returns INDETERMINATE and the inspector is asked
#: to re-shoot with a calibration card in frame.
MAX_USABLE_UNCERTAINTY = 0.10


class Scale(BaseModel):
    """Pixels-to-millimetres conversion recovered from a reference object."""

    mm_per_px: float = Field(gt=0)
    source: CalibrationSource
    relative_uncertainty: float = Field(ge=0, le=1)
    reference_detail: str | None = None
    """Human-readable note, e.g. 'ID-1 card, long edge 1043 px = 85.60 mm'."""

    @property
    def is_usable_for_legal_assertion(self) -> bool:
        return self.relative_uncertainty <= MAX_USABLE_UNCERTAINTY

    @classmethod
    def from_reference(
        cls,
        *,
        measured_px: float,
        known_mm: float,
        source: CalibrationSource,
        detail: str | None = None,
        extra_uncertainty: float = 0.0,
    ) -> "Scale":
        """Build a scale from a reference object of known physical size."""
        if measured_px <= 0:
            raise ValueError("measured_px must be positive")
        base = CALIBRATION_UNCERTAINTY[source]
        return cls(
            mm_per_px=known_mm / measured_px,
            source=source,
            # Uncertainties combine in quadrature: they are independent errors.
            relative_uncertainty=min(1.0, (base**2 + extra_uncertainty**2) ** 0.5),
            reference_detail=detail,
        )


class Measurement(BaseModel):
    """A millimetre quantity plus the interval we are willing to defend."""

    value_mm: float = Field(ge=0)
    ci_low_mm: float = Field(ge=0)
    ci_high_mm: float = Field(ge=0)
    source: CalibrationSource
    detail: str | None = None

    @model_validator(mode="after")
    def _check_interval(self) -> "Measurement":
        if not (self.ci_low_mm <= self.value_mm <= self.ci_high_mm):
            raise ValueError("value_mm must lie inside [ci_low_mm, ci_high_mm]")
        return self

    @classmethod
    def from_pixels(cls, px: float, scale: Scale, detail: str | None = None) -> "Measurement":
        value = px * scale.mm_per_px
        spread = value * scale.relative_uncertainty
        return cls(
            value_mm=value,
            ci_low_mm=max(0.0, value - spread),
            ci_high_mm=value + spread,
            source=scale.source,
            detail=detail or scale.reference_detail,
        )

    @property
    def relative_uncertainty(self) -> float:
        """Half-width of the interval as a fraction of the estimate."""
        if self.value_mm <= 0:
            return 1.0
        return (self.ci_high_mm - self.ci_low_mm) / (2 * self.value_mm)

    def at_least(self, threshold_mm: float) -> FindingStatus:
        """Decide whether this measurement clears a statutory minimum.

        The asymmetry is intentional, and it runs in two stages.

        First, a measurement too imprecise to defend can never produce a
        violation, however far below the threshold its midpoint happens to sit.
        An EAN-13 barcode read as though it were printed at 100% magnification
        can be wrong by a factor of two -- the interval may still land wholly
        under the threshold and yet mean nothing.

        Second, even with a trustworthy scale we assert a violation only when
        the whole interval sits below the threshold. If the interval spans it we
        say so, because the cost of a wrong FAIL is a manufacturer served with a
        notice they can overturn, and with them the credibility of every other
        finding we ever issue.
        """
        if self.ci_low_mm >= threshold_mm:
            return FindingStatus.PASS
        if self.relative_uncertainty > MAX_USABLE_UNCERTAINTY:
            return FindingStatus.INDETERMINATE
        if self.ci_high_mm < threshold_mm:
            return FindingStatus.FAIL
        return FindingStatus.INDETERMINATE

    def __str__(self) -> str:  # pragma: no cover - display helper
        margin = self.ci_high_mm - self.value_mm
        return f"{self.value_mm:.2f} mm (+/-{margin:.2f}, via {self.source})"
