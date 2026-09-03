"""Aggregations behind the regulator dashboard.

The point of this endpoint set is targeting. An officer has finite hours; these
queries tell them which category, which brand and which district are worth
spending them on -- which is the difference between enforcement that reacts to
complaints and enforcement that goes looking.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from astra_rules import RulePack

from ..config import settings
from ..db import get_session
from ..models import Scan

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
def summary(session: Annotated[Session, Depends(get_session)]) -> dict:
    total = session.scalar(select(func.count()).select_from(Scan)) or 0
    if not total:
        return {
            "total_scans": 0, "non_compliant": 0, "needs_review": 0,
            "compliance_rate": None, "critical_violations": 0,
            "undecided_rules": 0, "unusable_calibration_rate": None,
            "by_verdict": {}, "by_source": {},
        }

    def count_where(column, value) -> int:
        return session.scalar(
            select(func.count()).select_from(Scan).where(column == value)
        ) or 0

    non_compliant = count_where(Scan.verdict, "NON_COMPLIANT")
    compliant = count_where(Scan.verdict, "COMPLIANT")
    partial = count_where(Scan.verdict, "PARTIALLY_COMPLIANT")
    needs_review = count_where(Scan.verdict, "NEEDS_REVIEW")

    verdicts = dict(
        session.execute(select(Scan.verdict, func.count()).group_by(Scan.verdict)).all()
    )
    sources = dict(
        session.execute(select(Scan.source, func.count()).group_by(Scan.source)).all()
    )

    # Scans whose calibration could not sustain a millimetre finding. A high
    # figure is an operational signal, not a software fault: inspectors are not
    # putting a reference card in frame.
    poor_calibration = session.scalar(
        select(func.count()).select_from(Scan).where(
            Scan.calibration_source.in_(["BARCODE_ASSUMED", "NONE", None])
        )
    ) or 0

    decided = compliant + partial + non_compliant
    return {
        "total_scans": total,
        "non_compliant": non_compliant,
        "partially_compliant": partial,
        "compliant": compliant,
        "needs_review": needs_review,
        "compliance_rate": round(100 * compliant / decided, 1) if decided else None,
        "critical_violations": session.scalar(
            select(func.coalesce(func.sum(Scan.critical_violations), 0))
        ) or 0,
        "undecided_rules": session.scalar(
            select(func.coalesce(func.sum(Scan.indeterminate), 0))
        ) or 0,
        "unusable_calibration_rate": round(100 * poor_calibration / total, 1),
        "mean_compliance_score": round(
            session.scalar(select(func.avg(Scan.compliance_score))) or 0.0, 1
        ),
        "by_verdict": verdicts,
        "by_source": sources,
    }


@router.get("/by-rule")
def by_rule(
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(25, ge=1, le=100),
) -> list[dict]:
    """Which provisions are actually breached, most frequent first.

    Findings live inside the stored report rather than in their own table, so
    this counts in Python. At demo and pilot volumes that is the right trade:
    the report stays an immutable legal record, which matters more than the
    query being clever.
    """
    pack = RulePack.load(settings.active_rulepack)
    titles = {r.id: (r.title, r.citation, str(r.severity)) for r in pack.rules}

    failures: Counter[str] = Counter()
    undecided: Counter[str] = Counter()
    for (report,) in session.execute(select(Scan.report_json)):
        for finding in (report or {}).get("findings", []):
            if finding["status"] == "FAIL":
                failures[finding["rule_id"]] += 1
            elif finding["status"] == "INDETERMINATE":
                undecided[finding["rule_id"]] += 1

    rows = []
    for rule_id, count in failures.most_common(limit):
        title, citation, severity = titles.get(rule_id, (rule_id, "", "MAJOR"))
        rows.append({
            "rule_id": rule_id, "title": title, "citation": citation,
            "severity": severity, "violations": count,
            "undecided": undecided.get(rule_id, 0),
        })
    return rows


@router.get("/by-dimension")
def by_dimension(
    session: Annotated[Session, Depends(get_session)],
    dimension: Annotated[str, Query(pattern="^(brand|commodity_category|state|district|platform)$")],
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    """Worst offenders along one axis, ranked by critical violations."""
    column = getattr(Scan, dimension)
    stmt = (
        select(
            column,
            func.count().label("scans"),
            func.coalesce(func.sum(Scan.critical_violations), 0).label("critical"),
            func.avg(Scan.compliance_score).label("mean_score"),
        )
        .where(column.is_not(None))
        .group_by(column)
        .order_by(func.coalesce(func.sum(Scan.critical_violations), 0).desc())
        .limit(limit)
    )
    return [
        {
            "key": key, "scans": scans, "critical_violations": critical,
            "mean_compliance_score": round(mean or 0.0, 1),
        }
        for key, scans, critical, mean in session.execute(stmt).all()
    ]


@router.get("/heatmap")
def heatmap(
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(2000, ge=1, le=10000),
) -> list[dict]:
    """Geolocated scans for the map layer."""
    stmt = (
        select(
            Scan.id, Scan.latitude, Scan.longitude, Scan.verdict,
            Scan.critical_violations, Scan.brand, Scan.commodity_category,
            Scan.district, Scan.state,
        )
        .where(Scan.latitude.is_not(None), Scan.longitude.is_not(None))
        .order_by(Scan.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": row.id, "lat": row.latitude, "lon": row.longitude,
            "verdict": row.verdict, "critical": row.critical_violations,
            "brand": row.brand, "category": row.commodity_category,
            "district": row.district, "state": row.state,
            # Weight the map by seriousness, not merely by presence.
            "weight": 1 + row.critical_violations * 2,
        }
        for row in session.execute(stmt).all()
    ]
