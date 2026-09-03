"""Closed vocabularies shared across services.

These are contract values: they appear in the database, in the JSON API and in
rule-pack YAML, so renaming one is a breaking change.
"""

from __future__ import annotations

from enum import StrEnum


class FindingStatus(StrEnum):
    """Outcome of evaluating one rule against one package.

    ``INDETERMINATE`` is deliberately a first-class result, not an error. A
    measurement whose confidence interval straddles the legal threshold must
    never be reported as a violation -- an inspector can re-shoot the photo with
    a calibration card, but a wrongly-issued notice damages a manufacturer.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"
    EXEMPT = "EXEMPT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Severity(StrEnum):
    """How hard a failure should be pushed at the adjudicating officer.

    ``ADVISORY`` exists so that pedantic irregularities (``100 gms.`` instead of
    ``100 g``) never crowd out a missing MRP in the officer's queue.
    """

    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    ADVISORY = "ADVISORY"


class PackageShape(StrEnum):
    """Drives the Rule 9(4) principal-display-panel area formula."""

    RECTANGULAR = "RECTANGULAR"
    CYLINDRICAL = "CYLINDRICAL"
    OTHER = "OTHER"


class PrintMethod(StrEnum):
    """Selects which column of the Rule 9 height tables applies."""

    PRINTED = "PRINTED"
    EMBOSSED = "EMBOSSED"  # blown, formed, moulded, embossed or perforated


class Script(StrEnum):
    """Rule 9(1) permits declarations in Devanagari (Hindi) or English."""

    LATIN = "LATIN"
    DEVANAGARI = "DEVANAGARI"
    OTHER = "OTHER"


class CalibrationSource(StrEnum):
    """Where the pixels-to-millimetres scale came from.

    Ordered best-first. Every measurement records which one produced it, because
    a millimetre figure is only as trustworthy as its reference object.
    """

    ARUCO = "ARUCO"                        # printed fiducial, ~1%
    ID1_CARD = "ID1_CARD"                  # ISO/IEC 7810 ID-1, 85.60x53.98mm, ~1-2%
    DECLARED_DIMENSION = "DECLARED_DIMENSION"  # dimensions from the listing, ~3-5%
    BARCODE_ASSUMED = "BARCODE_ASSUMED"    # EAN-13 assumed 100% magnification, >=20%
    MANUAL = "MANUAL"                      # inspector typed a known width
    NONE = "NONE"                          # no scale -- mm rules go INDETERMINATE


class PackageType(StrEnum):
    RETAIL = "RETAIL"
    WHOLESALE = "WHOLESALE"


class ScanSource(StrEnum):
    FIELD_INSPECTION = "FIELD_INSPECTION"
    ECOMMERCE_LISTING = "ECOMMERCE_LISTING"
    BRAND_SELF_CHECK = "BRAND_SELF_CHECK"
