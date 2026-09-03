"""Database tables.

Two decisions here are worth stating plainly.

Reports are stored as their full JSON alongside the columns we query on. The
findings a scan produced are a legal record: once an officer has acted on them
they must never change, even if the rule pack, the extractor or this schema
moves on. Normalising them into rows would tempt exactly that.

Nothing is ever hard-deleted. An inspection that disappears is an inspection
that cannot be audited, so dispositions are recorded as status transitions and
overrides are appended, never applied in place.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Scan(Base):
    """One assessment of one package."""

    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Provenance -- the chain of custody an officer will be asked about.
    image_sha256: Mapped[str] = mapped_column(String(64), index=True)
    image_path: Mapped[str] = mapped_column(String(512))
    inspector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    source: Mapped[str] = mapped_column(String(32), default="FIELD_INSPECTION", index=True)
    rulepack: Mapped[str] = mapped_column(String(64), index=True)
    engine_version: Mapped[str] = mapped_column(String(16), default="0.1.0")

    # Where and what -- the columns the dashboard aggregates on.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    district: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    premises: Mapped[str | None] = mapped_column(String(256), nullable=True)

    brand: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    commodity_category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    listing_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Outcome, denormalised for querying.
    verdict: Mapped[str] = mapped_column(String(32), index=True)
    compliance_score: Mapped[float] = mapped_column(Float, default=0.0)
    critical_violations: Mapped[int] = mapped_column(Integer, default=0)
    major_violations: Mapped[int] = mapped_column(Integer, default=0)
    advisory_violations: Mapped[int] = mapped_column(Integer, default=0)
    indeterminate: Mapped[int] = mapped_column(Integer, default=0)
    calibration_source: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    # The immutable record.
    report_json: Mapped[dict] = mapped_column(JSON)
    fields_json: Mapped[dict] = mapped_column(JSON)

    status: Mapped[str] = mapped_column(String(32), default="NEW", index=True)
    """NEW -> UNDER_REVIEW -> CONFIRMED | DISMISSED. Set by an officer, never
    by the engine."""

    overrides: Mapped[list["Override"]] = relationship(back_populates="scan")
    notices: Mapped[list["Notice"]] = relationship(back_populates="scan")


Index("ix_scans_created_verdict", Scan.created_at, Scan.verdict)


class Override(Base):
    """An officer disagreeing with the engine.

    Every one of these is a training example and an accountability record. The
    engine's original finding stays in ``report_json`` untouched; this table
    says what a human decided instead, and why.
    """

    __tablename__ = "overrides"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(64), index=True)

    engine_status: Mapped[str] = mapped_column(String(24))
    officer_status: Mapped[str] = mapped_column(String(24))
    officer_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)

    scan: Mapped[Scan] = relationship(back_populates="overrides")


class Notice(Base):
    """A draft notice, and the record of an officer signing it.

    ASTRA drafts; only a Legal Metrology Officer issues. The distinction is
    enforced here: a notice has no legal effect until ``signed_by`` is set, and
    the drafting engine can never set it.
    """

    __tablename__ = "notices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    reference: Mapped[str] = mapped_column(String(64), unique=True)

    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    """DRAFT -> SIGNED -> SERVED -> DISPOSED."""

    addressee: Mapped[str | None] = mapped_column(String(256), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    cited_rules: Mapped[list] = mapped_column(JSON, default=list)

    signed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    scan: Mapped[Scan] = relationship(back_populates="notices")
