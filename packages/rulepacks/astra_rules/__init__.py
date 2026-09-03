"""Law-as-code: versioned rule packs plus the deterministic evaluator."""

from .checks import CHECKS, CheckContext, CheckOutcome, check
from .engine import ENGINE_VERSION, active_exemptions, evaluate, matches, summarise
from .pack import ExemptionSpec, RulePack, RuleSpec, ThresholdBand, ThresholdTable

__all__ = [
    "CHECKS",
    "ENGINE_VERSION",
    "CheckContext",
    "CheckOutcome",
    "ExemptionSpec",
    "RulePack",
    "RuleSpec",
    "ThresholdBand",
    "ThresholdTable",
    "active_exemptions",
    "check",
    "evaluate",
    "matches",
    "summarise",
]
