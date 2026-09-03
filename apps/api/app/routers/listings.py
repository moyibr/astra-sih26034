"""Bulk assessment of e-commerce listings.

The scale argument for the whole system lives here: one officer uploading a
catalogue export can assess a platform's entire range against the rules in
force, including Rule 6(10A), which is a question about the platform's own
search architecture rather than about any individual pack.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from astra_rules import evaluate
from vision.adapters import listing as adapter

from ..config import settings
from ..db import get_session
from ..models import Scan

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/listings", tags=["listings"])

MAX_CSV_BYTES = 10 * 1024 * 1024


class ImportResult(BaseModel):
    imported: int
    non_compliant: int
    partially_compliant: int
    needs_review: int
    compliant: int
    platform_filter_violations: int
    scan_ids: list[str]


@router.get("/sample")
def sample_csv() -> dict:
    """The shape a catalogue export should take."""
    return {
        "columns": sorted(adapter.KNOWN_COLUMNS),
        "notes": (
            "Only listing_id is required. has_country_filter and "
            "country_filter_sortable describe the platform's listing pages, not "
            "the product, and drive the Rule 6(10A) check. Leave them blank if "
            "the platform has not been audited -- blank means 'not assessed', "
            "which is not the same as 'absent'."
        ),
        "example": adapter.sample_csv(),
    }


@router.post("/import", response_model=ImportResult, status_code=201)
async def import_catalogue(
    session: Annotated[Session, Depends(get_session)],
    file: Annotated[UploadFile, File(description="Catalogue export, CSV")],
    dry_run: Annotated[bool, Query(description="Assess without persisting")] = False,
) -> ImportResult:
    payload = await file.read()
    if not payload:
        raise HTTPException(400, "empty upload")
    if len(payload) > MAX_CSV_BYTES:
        raise HTTPException(413, "catalogue exceeds 10 MB")

    try:
        listings = adapter.parse_csv(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(400, f"could not read the CSV: {exc}") from exc

    if not listings:
        raise HTTPException(400, "the CSV contained no rows")

    counts = {
        "NON_COMPLIANT": 0,
        "PARTIALLY_COMPLIANT": 0,
        "NEEDS_REVIEW": 0,
        "COMPLIANT": 0,
    }
    filter_violations = 0
    scan_ids: list[str] = []

    for item in listings:
        fields = adapter.to_fields(item)
        report = evaluate(fields, settings.active_rulepack)

        counts[report.summary.verdict] = counts.get(report.summary.verdict, 0) + 1
        if any(
            f.rule_id == "R6-10A-coo-filter" and f.is_violation for f in report.findings
        ):
            filter_violations += 1

        if dry_run:
            continue

        session.merge(
            Scan(
                id=fields.scan_id,
                image_sha256=fields.image_sha256,
                # There is no photograph; the listing text is what was assessed.
                image_path="",
                source="ECOMMERCE_LISTING",
                rulepack=report.rulepack,
                engine_version=report.engine_version,
                brand=item.brand,
                commodity_category=item.category,
                platform=item.platform,
                listing_url=item.url,
                verdict=report.summary.verdict,
                compliance_score=report.summary.compliance_score,
                critical_violations=report.summary.critical_violations,
                major_violations=report.summary.major_violations,
                advisory_violations=report.summary.advisory_violations,
                indeterminate=report.summary.indeterminate,
                calibration_source=None,
                report_json=report.model_dump(mode="json"),
                fields_json=fields.model_dump(mode="json"),
            )
        )
        scan_ids.append(fields.scan_id)

    session.flush()
    log.info(
        "imported %d listings (%d non-compliant, %d failing the 6(10A) filter check)",
        len(listings), counts["NON_COMPLIANT"], filter_violations,
    )

    return ImportResult(
        imported=len(listings),
        non_compliant=counts["NON_COMPLIANT"],
        partially_compliant=counts["PARTIALLY_COMPLIANT"],
        needs_review=counts["NEEDS_REVIEW"],
        compliant=counts["COMPLIANT"],
        platform_filter_violations=filter_violations,
        scan_ids=scan_ids,
    )
