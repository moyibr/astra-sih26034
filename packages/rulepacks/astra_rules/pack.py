"""Loading and modelling a versioned rule pack.

A pack is a snapshot of the law at a moment in time. Reports pin the pack that
judged them (``lmpc-2011@2026.07.01``), so a scan taken today can be re-evaluated
years later and produce byte-identical findings even after the rules have moved
on -- which is what makes a finding defensible in adjudication rather than merely
plausible.
"""

from __future__ import annotations

import functools
import pathlib
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from astra_schema import PrintMethod, Severity

PACKS_DIR = pathlib.Path(__file__).resolve().parent.parent / "packs"


class ThresholdBand(BaseModel):
    """One row of a Rule 9 height table."""

    upto: float | None = None
    """Inclusive upper bound of the band; ``None`` means "and above"."""
    printed: float
    embossed: float

    def height_for(self, method: PrintMethod) -> float:
        return self.embossed if method is PrintMethod.EMBOSSED else self.printed


class ThresholdTable(BaseModel):
    """A statutory lookup from panel area to minimum glyph height."""

    description: str = ""
    key: str
    unit: str = "mm"
    bands: list[ThresholdBand]

    def threshold_for(self, key_value: float, method: PrintMethod) -> tuple[float, ThresholdBand]:
        """Return the minimum height in mm for a given panel area.

        Band boundaries are treated as inclusive of their upper value, so a panel
        of exactly 50 cm2 falls in the ``upto: 50`` band and attracts the lower
        requirement. Where the drafting is ambiguous we resolve it in favour of
        the person who would be penalised, which is the ordinary approach to a
        penal provision.
        """
        for band in self.bands:
            if band.upto is None or key_value <= band.upto:
                return band.height_for(method), band
        last = self.bands[-1]
        return last.height_for(method), last


class CheckSpec(BaseModel):
    """The operator to run plus whatever parameters it needs.

    Extra keys are preserved verbatim: each check declares its own parameters in
    YAML, and the engine passes them straight through.
    """

    model_config = ConfigDict(extra="allow")

    op: str

    def params(self) -> dict[str, Any]:
        extra = dict(self.__pydantic_extra__ or {})
        return extra


class RuleSpec(BaseModel):
    id: str
    citation: str
    title: str
    severity: Severity
    check: CheckSpec

    verification: Literal["VERIFIED", "NEEDS_GAZETTE_CHECK"] = "NEEDS_GAZETTE_CHECK"
    applies_when: dict[str, Any] = Field(default_factory=dict)
    requires: list[str] = Field(default_factory=list)
    """Rules that must not have failed for this one to be meaningful.

    There is no point telling a packer their price is missing the words
    'inclusive of all taxes' when we could not find a price at all.
    """
    requires_calibration: bool = False
    scope: Literal["package", "platform"] = "package"
    remedy: str | None = None
    note: str | None = None


class ExemptionSpec(BaseModel):
    """A Rule 26 style carve-out, applied before any rule is evaluated."""

    id: str
    citation: str
    reason: str
    when: dict[str, Any]
    exempts: list[str]
    """Rule ids or glob-ish prefixes ending in ``*``."""
    verification: Literal["VERIFIED", "NEEDS_GAZETTE_CHECK"] = "NEEDS_GAZETTE_CHECK"

    def covers(self, rule_id: str) -> bool:
        for pattern in self.exempts:
            if pattern.endswith("*"):
                if rule_id.startswith(pattern[:-1]):
                    return True
            elif pattern == rule_id:
                return True
        return False


class RulePack(BaseModel):
    pack: str
    version: str
    title: str
    jurisdiction: str = "IN"
    in_force_from: str
    supersedes: str | None = None
    gazette_refs: list[str] = Field(default_factory=list)

    tables: dict[str, ThresholdTable] = Field(default_factory=dict)
    units: dict[str, Any] = Field(default_factory=dict)
    exemptions: list[ExemptionSpec] = Field(default_factory=list)
    rules: list[RuleSpec] = Field(default_factory=list)

    @property
    def identifier(self) -> str:
        return f"{self.pack}@{self.version}"

    def rule(self, rule_id: str) -> RuleSpec | None:
        return next((r for r in self.rules if r.id == rule_id), None)

    def canonical_unit_for(self, printed: str) -> tuple[str | None, bool]:
        """Map a printed unit to its SI symbol.

        Returns ``(symbol, is_exact)``. ``is_exact`` is False when the pack only
        recognised the token as a tolerated variant such as ``gms.`` -- the
        quantity is still understood, but the symbol is irregular.
        """
        token = printed.strip()
        canonical = self.units.get("canonical", {})
        for family in canonical.values():
            if token in family:
                return token, True

        variants: dict[str, list[str]] = self.units.get("tolerated_variants", {})
        lowered = token.lower()
        for symbol, forms in variants.items():
            if lowered == symbol.lower() or lowered in {f.lower() for f in forms}:
                return symbol, token == symbol
        return None, False

    def base_multiplier(self, symbol: str) -> float | None:
        """Grams per unit for mass, millilitres per unit for volume."""
        for family in self.units.get("canonical", {}).values():
            if symbol in family:
                return float(family[symbol])
        return None

    # -- loading ------------------------------------------------------------
    @classmethod
    def from_yaml(cls, path: str | pathlib.Path) -> "RulePack":
        data = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)

    @classmethod
    def load(cls, identifier: str) -> "RulePack":
        """Load by ``name@version``, e.g. ``lmpc-2011@2026.07.01``."""
        return _load_cached(identifier)

    @classmethod
    def available(cls) -> list[str]:
        found: list[str] = []
        for pack_dir in sorted(PACKS_DIR.glob("*")):
            if not pack_dir.is_dir():
                continue
            for f in sorted(pack_dir.glob("v*.yaml")):
                found.append(f"{pack_dir.name}@{f.stem.lstrip('v')}")
        return found


@functools.lru_cache(maxsize=8)
def _load_cached(identifier: str) -> RulePack:
    if "@" not in identifier:
        raise ValueError(f"rule pack identifier must be 'name@version', got {identifier!r}")
    name, version = identifier.split("@", 1)
    path = PACKS_DIR / name / f"v{version}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"rule pack {identifier!r} not found at {path}. Available: {RulePack.available()}"
        )
    return RulePack.from_yaml(path)
