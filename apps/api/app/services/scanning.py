"""Running a scan and persisting what it found.

The order of operations matters and is deliberate: the image is written to disk
and hashed *before* anything is analysed. If the pipeline then falls over, the
evidence still exists and the scan can be replayed. An inspection that vanishes
because the OCR crashed is an inspection that cannot be audited.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import pathlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from astra_rules import evaluate
from astra_schema import (
    ExtractedFields,
    PackageShape,
    PackageType,
    PrintMethod,
    Report,
    ScanSource,
)
from ..config import settings
from ..models import Notice, Scan

log = logging.getLogger(__name__)


class ScanningUnavailable(RuntimeError):
    """Raised when a scan is requested on a deployment that cannot do OCR."""


@functools.cache
def scanning_available() -> bool:
    """Whether this deployment can read a photograph.

    Importing the vision pipeline is what pulls in OpenCV, ONNX Runtime and the
    OCR models -- around 240 MB of wheels. Exactly one code path needs them, so
    the import happens here rather than at module scope, and a deployment
    without them still serves recorded inspections, the analytics, the rule
    pack and the e-commerce audit perfectly well.

    That is not a degraded mode so much as an honest one: on a tenth of a CPU a
    scan takes a minute, so the public deployment does not pretend to offer it
    and says as much through /health.
    """
    if not settings.scanning_enabled:
        log.info("scanning disabled by configuration")
        return False
    try:
        import vision.pipeline.analyse  # noqa: F401
    except ImportError as exc:
        log.info("scanning unavailable: %s", exc)
        return False
    return True


def store_image(image_bytes: bytes) -> tuple[str, pathlib.Path]:
    """Write the image under its own digest, so identical uploads collapse."""
    digest = hashlib.sha256(image_bytes).hexdigest()
    settings.ensure_dirs()
    path = settings.upload_dir / f"{digest}.bin"
    if not path.exists():
        path.write_bytes(image_bytes)
    return digest, path


def run_scan(
    session: Session,
    image_bytes: bytes,
    *,
    inspector_id: str | None = None,
    source: ScanSource = ScanSource.FIELD_INSPECTION,
    package_type: PackageType = PackageType.RETAIL,
    shape: PackageShape = PackageShape.OTHER,
    print_method: PrintMethod = PrintMethod.PRINTED,
    height_mm: float | None = None,
    width_mm: float | None = None,
    diameter_mm: float | None = None,
    commodity_category: str | None = None,
    is_perishable: bool = False,
    brand: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    state: str | None = None,
    district: str | None = None,
    premises: str | None = None,
    platform: str | None = None,
    listing_url: str | None = None,
) -> tuple[Scan, Report, ExtractedFields]:
    if not scanning_available():
        raise ScanningUnavailable(
            "This deployment cannot read photographs. Live scanning needs the "
            "OCR stack, which is omitted here because the free hosting tier "
            "provides a tenth of a CPU and a scan would take about a minute. "
            "Run the API locally to scan; everything else works here."
        )

    digest, path = store_image(image_bytes)

    # Imported here, not at module scope: this single line is what would
    # otherwise make OpenCV and ONNX Runtime mandatory for the whole service.
    from vision.pipeline.analyse import analyse

    fields = analyse(
        image_bytes,
        scan_source=source,
        package_type=package_type,
        shape=shape,
        print_method=print_method,
        height_mm=height_mm,
        width_mm=width_mm,
        diameter_mm=diameter_mm,
        commodity_category=commodity_category,
        is_perishable=is_perishable,
        use_llm_normaliser=settings.llm_normaliser_enabled,
    )
    report = evaluate(fields, settings.active_rulepack)

    scan = Scan(
        id=fields.scan_id,
        image_sha256=digest,
        # The bare filename, not an absolute path: a path from the machine
        # that produced a scan means nothing inside a container, and the demo
        # dataset ships between the two.
        image_path=path.name,
        inspector_id=inspector_id,
        source=str(source),
        rulepack=report.rulepack,
        engine_version=report.engine_version,
        latitude=latitude,
        longitude=longitude,
        state=state,
        district=district,
        premises=premises,
        brand=brand,
        commodity_category=commodity_category,
        listing_url=listing_url,
        platform=platform,
        verdict=report.summary.verdict,
        compliance_score=report.summary.compliance_score,
        critical_violations=report.summary.critical_violations,
        major_violations=report.summary.major_violations,
        advisory_violations=report.summary.advisory_violations,
        indeterminate=report.summary.indeterminate,
        calibration_source=str(fields.scale.source) if fields.scale else None,
        report_json=report.model_dump(mode="json"),
        fields_json=fields.model_dump(mode="json"),
    )
    session.add(scan)
    session.flush()

    log.info(
        "scan %s -> %s (%d critical) via %s",
        scan.id, scan.verdict, scan.critical_violations, scan.calibration_source,
    )
    return scan, report, fields


NOTICE_TEMPLATE = """\
OFFICE OF THE CONTROLLER OF LEGAL METROLOGY
{state}

NOTICE UNDER THE LEGAL METROLOGY ACT, 2009 AND THE
LEGAL METROLOGY (PACKAGED COMMODITIES) RULES, 2011

Reference : {reference}
Date      : {date}
To        : {addressee}

Whereas an inspection of the pre-packaged commodity described below was carried
out{premises_clause}, and whereas the declarations on the said package were
examined against the Legal Metrology (Packaged Commodities) Rules, 2011 as in
force on the date of inspection ({rulepack}), the following contraventions are
alleged:

{violations}

The evidence relied upon comprises the photograph of the package bearing digest
{digest}, together with the measurements and extracted declarations recorded
against this inspection.

You are hereby called upon to show cause why proceedings should not be initiated
in respect of the above contraventions. A written representation may be
submitted to this office within fifteen (15) days of service of this notice.

{measurement_note}
                                        ______________________________
                                        Legal Metrology Officer
                                        (This notice has no effect until signed)
"""


def draft_notice(session: Session, scan: Scan, *, addressee: str | None = None) -> Notice:
    """Prepare a notice for an officer to review, amend and sign.

    Nothing here issues anything. The draft is generated in full so the officer
    is editing rather than typing, but it carries no authority until a named
    officer signs it -- which the engine cannot do on their behalf.
    """
    report = Report.model_validate(scan.report_json)
    violations = report.violations()

    if not violations:
        raise ValueError("no violations were found on this scan; there is nothing to serve")

    lines: list[str] = []
    for index, finding in enumerate(violations, start=1):
        lines.append(f"{index}. {finding.title}  [{finding.severity}]")
        lines.append(f"   Provision : {finding.citation}")
        if finding.required:
            lines.append(f"   Required  : {finding.required}")
        if finding.measured:
            lines.append(f"   Found     : {finding.measured}")
        lines.append(f"   Particulars: {finding.explanation}")
        lines.append("")

    measurement_note = ""
    if report.summary.indeterminate:
        # Saying this out loud protects the notice. An officer who is not told
        # which checks were undecided may unknowingly assert more than the
        # evidence supports.
        measurement_note = (
            f"Note: {report.summary.indeterminate} further check(s) could not be "
            "determined from the evidence available and are NOT alleged in this "
            "notice.\n\n"
        )

    body = NOTICE_TEMPLATE.format(
        state=(scan.state or "").upper(),
        reference=f"LM/{datetime.now(timezone.utc):%Y}/{scan.id[:8].upper()}",
        date=f"{datetime.now(timezone.utc):%d %B %Y}",
        addressee=addressee or scan.brand or "The Manufacturer / Packer / Importer",
        premises_clause=f" at {scan.premises}" if scan.premises else "",
        rulepack=scan.rulepack,
        violations="\n".join(lines).rstrip(),
        digest=scan.image_sha256,
        measurement_note=measurement_note,
    )

    notice = Notice(
        scan_id=scan.id,
        reference=f"LM/{datetime.now(timezone.utc):%Y}/{scan.id[:8].upper()}",
        addressee=addressee or scan.brand,
        body=body,
        cited_rules=[f.rule_id for f in violations],
        status="DRAFT",
    )
    session.add(notice)
    session.flush()
    return notice
