"""Exposing the law the engine is applying.

A regulator should never have to take our word for which rules ran. These
endpoints publish the active pack in full -- every citation, every threshold,
every exemption, and which provisions are still awaiting confirmation against
the gazette text.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from astra_rules import CHECKS, RulePack

from ..config import settings

router = APIRouter(prefix="/api/rulepacks", tags=["rulepacks"])


@router.get("")
def list_packs() -> dict:
    return {"active": settings.active_rulepack, "available": RulePack.available()}


@router.get("/active")
def active_pack() -> dict:
    return _describe(RulePack.load(settings.active_rulepack))


@router.get("/{identifier:path}")
def get_pack(identifier: str) -> dict:
    try:
        return _describe(RulePack.load(identifier))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc


def _describe(pack: RulePack) -> dict:
    return {
        "identifier": pack.identifier,
        "title": pack.title,
        "jurisdiction": pack.jurisdiction,
        "in_force_from": pack.in_force_from,
        "gazette_refs": pack.gazette_refs,
        "tables": {
            name: {
                "description": table.description,
                "key": table.key,
                "unit": table.unit,
                "bands": [b.model_dump() for b in table.bands],
            }
            for name, table in pack.tables.items()
        },
        "exemptions": [
            {"id": e.id, "citation": e.citation, "reason": e.reason,
             "exempts": e.exempts, "verification": e.verification}
            for e in pack.exemptions
        ],
        "rules": [
            {
                "id": r.id, "title": r.title, "citation": r.citation,
                "severity": str(r.severity), "scope": r.scope,
                "requires_calibration": r.requires_calibration,
                "applies_when": r.applies_when, "remedy": r.remedy, "note": r.note,
                "verification": r.verification,
                "check": r.check.op,
                "implemented": r.check.op in CHECKS,
            }
            for r in pack.rules
        ],
        "counts": {
            "rules": len(pack.rules),
            "exemptions": len(pack.exemptions),
            "awaiting_gazette_check": sum(
                1 for r in pack.rules if r.verification == "NEEDS_GAZETTE_CHECK"
            ),
        },
    }
