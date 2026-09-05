"""Scan submission, retrieval, officer disposition and notice drafting."""

from __future__ import annotations

import logging
import pathlib
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from astra_schema import PackageShape, PackageType, PrintMethod, ScanSource

from ..auth import CurrentOfficer
from ..config import settings
from ..db import get_session
from ..ratelimit import limit_scans, limit_writes
from ..models import Notice, Override, Scan
from ..services import scanning, signing
from ..uploads import read_capped

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["scans"])

MAX_IMAGE_BYTES = 20 * 1024 * 1024


class ScanSummary(BaseModel):
    id: str
    created_at: datetime
    verdict: str
    compliance_score: float
    critical_violations: int
    major_violations: int
    advisory_violations: int
    indeterminate: int
    calibration_source: str | None
    source: str
    status: str
    brand: str | None
    commodity_category: str | None
    state: str | None
    district: str | None
    premises: str | None
    latitude: float | None
    longitude: float | None
    rulepack: str

    model_config = {"from_attributes": True}


class ScanDetail(ScanSummary):
    image_sha256: str
    report: dict
    fields: dict
    overrides: list[dict] = Field(default_factory=list)
    notices: list[dict] = Field(default_factory=list)


class OverrideRequest(BaseModel):
    rule_id: str
    officer_status: str
    reason: str = Field(min_length=8)
    """Required, and required to be substantive.

    There is deliberately no officer_id here. It used to be one, which meant
    the audit trail recorded whatever string the caller chose -- so an override
    could be attributed to any officer by anyone. It now comes from the bearer
    token and cannot be contradicted by the request."""
    """Required, and required to be substantive. An override without a stated
    reason is indistinguishable from a mistake when it is read back a year
    later."""


class NoticeRequest(BaseModel):
    addressee: str | None = None


class SignRequest(BaseModel):
    """Empty on purpose: the signature identifies itself.

    Only a Legal Metrology Officer may issue a notice, so who signed it is the
    single most consequential field in the system. It is taken from the
    authenticated officer, never from the body."""


@router.post("/scans", response_model=ScanDetail, status_code=201,
             dependencies=[Depends(limit_scans)])
async def create_scan(
    session: Annotated[Session, Depends(get_session)],
    officer: CurrentOfficer,
    image: Annotated[UploadFile, File(description="Photograph of the package")],
    source: Annotated[ScanSource, Form()] = ScanSource.FIELD_INSPECTION,
    package_type: Annotated[PackageType, Form()] = PackageType.RETAIL,
    shape: Annotated[PackageShape, Form()] = PackageShape.OTHER,
    print_method: Annotated[PrintMethod, Form()] = PrintMethod.PRINTED,
    height_mm: Annotated[float | None, Form()] = None,
    width_mm: Annotated[float | None, Form()] = None,
    diameter_mm: Annotated[float | None, Form()] = None,
    commodity_category: Annotated[str | None, Form()] = None,
    is_perishable: Annotated[bool, Form()] = False,
    brand: Annotated[str | None, Form()] = None,
    latitude: Annotated[float | None, Form()] = None,
    longitude: Annotated[float | None, Form()] = None,
    state: Annotated[str | None, Form()] = None,
    district: Annotated[str | None, Form()] = None,
    premises: Annotated[str | None, Form()] = None,
    platform: Annotated[str | None, Form()] = None,
    listing_url: Annotated[str | None, Form()] = None,
) -> ScanDetail:
    payload = await read_capped(image, MAX_IMAGE_BYTES, what="image")

    try:
        scan, _report, _fields = scanning.run_scan(
            session, payload,
            inspector_id=officer.id, source=source, package_type=package_type,
            shape=shape, print_method=print_method, height_mm=height_mm,
            width_mm=width_mm, diameter_mm=diameter_mm,
            commodity_category=commodity_category, is_perishable=is_perishable,
            brand=brand, latitude=latitude, longitude=longitude, state=state,
            district=district, premises=premises, platform=platform,
            listing_url=listing_url,
        )
    except scanning.ScanningUnavailable as exc:
        # 503, not 500: nothing is broken, this deployment simply does not
        # offer the capability. The message tells the caller where it does.
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return _detail(scan)


@router.get("/scans", response_model=list[ScanSummary])
def list_scans(
    session: Annotated[Session, Depends(get_session)],
    verdict: str | None = None,
    status: str | None = None,
    state: str | None = None,
    brand: str | None = None,
    commodity_category: str | None = None,
    source: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[ScanSummary]:
    stmt = select(Scan).order_by(Scan.created_at.desc())
    for column, value in (
        (Scan.verdict, verdict), (Scan.status, status), (Scan.state, state),
        (Scan.brand, brand), (Scan.commodity_category, commodity_category),
        (Scan.source, source),
    ):
        if value:
            stmt = stmt.where(column == value)

    rows = session.scalars(stmt.limit(limit).offset(offset)).all()
    return [ScanSummary.model_validate(r) for r in rows]


@router.get("/scans/{scan_id}", response_model=ScanDetail)
def get_scan(scan_id: str, session: Annotated[Session, Depends(get_session)]) -> ScanDetail:
    return _detail(_require(session, scan_id))


@router.get("/scans/{scan_id}/image")
def get_scan_image(scan_id: str, session: Annotated[Session, Depends(get_session)]):
    """Serve the original image a scan was drawn from.

    Stored paths are bare filenames resolved against the upload directory, so
    the demo dataset built on one machine still finds its evidence inside a
    container. Absolute paths from older records are honoured if they happen to
    exist, and otherwise fall back to the same lookup.
    """
    scan = _require(session, scan_id)
    if not scan.image_path:
        raise HTTPException(404, "this scan has no image; it was assessed from listing text")

    candidate = pathlib.Path(scan.image_path)
    if not candidate.is_absolute() or not candidate.exists():
        candidate = settings.upload_dir / candidate.name
    if not candidate.exists():
        raise HTTPException(404, "the evidence image is no longer on disk")

    return FileResponse(candidate, media_type="image/jpeg")


@router.post("/scans/{scan_id}/override", response_model=ScanDetail, dependencies=[Depends(limit_writes)])
def override_finding(
    scan_id: str,
    body: OverrideRequest,
    session: Annotated[Session, Depends(get_session)],
    officer: CurrentOfficer,
) -> ScanDetail:
    """Record an officer disagreeing with the engine.

    The engine's original finding is left exactly as it was. This appends what
    a human decided instead, which is both the accountability record and the
    training signal for improving the extractor.
    """
    scan = _require(session, scan_id)
    findings = {f["rule_id"]: f for f in scan.report_json.get("findings", [])}
    if body.rule_id not in findings:
        raise HTTPException(404, f"scan has no finding for rule {body.rule_id}")

    session.add(
        Override(
            scan_id=scan.id,
            rule_id=body.rule_id,
            engine_status=findings[body.rule_id]["status"],
            officer_status=body.officer_status,
            officer_id=officer.id,
            reason=body.reason,
        )
    )
    scan.status = "UNDER_REVIEW"
    session.flush()
    return _detail(scan)


@router.post("/scans/{scan_id}/status", response_model=ScanDetail, dependencies=[Depends(limit_writes)])
def set_status(
    scan_id: str,
    status: Annotated[str, Query(pattern="^(NEW|UNDER_REVIEW|CONFIRMED|DISMISSED)$")],
    session: Annotated[Session, Depends(get_session)],
    officer: CurrentOfficer,
) -> ScanDetail:
    scan = _require(session, scan_id)
    scan.status = status
    session.flush()
    return _detail(scan)


@router.post("/scans/{scan_id}/notice", status_code=201, dependencies=[Depends(limit_writes)])
def create_notice(
    scan_id: str,
    body: NoticeRequest,
    session: Annotated[Session, Depends(get_session)],
    officer: CurrentOfficer,
) -> dict:
    scan = _require(session, scan_id)
    try:
        notice = scanning.draft_notice(session, scan, addressee=body.addressee)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _notice_dict(notice)


@router.post("/notices/{notice_id}/sign", dependencies=[Depends(limit_writes)])
def sign_notice(
    notice_id: str,
    body: SignRequest,
    session: Annotated[Session, Depends(get_session)],
    officer: CurrentOfficer,
) -> dict:
    """Only this endpoint gives a notice legal effect, and only a named officer
    can call it. The drafting path deliberately cannot reach it."""
    notice = session.get(Notice, notice_id)
    if notice is None:
        raise HTTPException(404, "notice not found")
    if notice.status != "DRAFT":
        raise HTTPException(409, f"notice is already {notice.status}")

    notice.signed_by = officer.id
    notice.signed_at = datetime.now(timezone.utc)
    notice.status = "SIGNED"
    notice.signature = signing.sign(
        reference=notice.reference,
        scan_digest=notice.scan.image_sha256,
        officer_id=officer.id,
        signed_at=notice.signed_at,
        body=notice.body,
    )
    session.flush()
    return _notice_dict(notice)


# -- helpers -----------------------------------------------------------------


def _require(session: Session, scan_id: str) -> Scan:
    scan = session.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(404, "scan not found")
    return scan


def _notice_dict(notice: Notice) -> dict:
    return {
        "id": notice.id,
        "reference": notice.reference,
        "status": notice.status,
        "addressee": notice.addressee,
        "cited_rules": notice.cited_rules,
        "body": notice.body,
        "signed_by": notice.signed_by,
        "signed_at": notice.signed_at,
        "created_at": notice.created_at,
    }


def _detail(scan: Scan) -> ScanDetail:
    return ScanDetail(
        **ScanSummary.model_validate(scan).model_dump(),
        image_sha256=scan.image_sha256,
        report=scan.report_json,
        fields=scan.fields_json,
        overrides=[
            {
                "rule_id": o.rule_id, "engine_status": o.engine_status,
                "officer_status": o.officer_status, "officer_id": o.officer_id,
                "reason": o.reason, "created_at": o.created_at,
            }
            for o in scan.overrides
        ],
        notices=[_notice_dict(n) for n in scan.notices],
    )
