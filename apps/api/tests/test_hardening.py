"""Limits that hold when the caller is careless or hostile.

Each of these covers a defence that was documented but not enforced: a size
limit consulted after the body was already in memory, a rate limit that did not
exist, and a secret_key that Render generated for nothing to read.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import ratelimit
from app.config import settings
from app.services import signing

TOKEN = "hardening-token"


@pytest.fixture
def officer(monkeypatch):
    monkeypatch.setattr(settings, "writes_enabled", True)
    monkeypatch.setattr(settings, "officers", f"{TOKEN}:LMO-0007:Anita Rao")
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def clear_limits():
    ratelimit._hits.clear()
    yield
    ratelimit._hits.clear()


# -- uploads -----------------------------------------------------------------


def test_an_oversized_image_is_refused(client, officer):
    """413 rather than an out-of-memory container.

    The check used to run after `await file.read()`, so the body was resident
    before its size was known -- on a 512 MB instance that is the whole budget
    spent by a caller who chose to spend it.
    """
    payload = b"\xff\xd8\xff" + b"0" * (21 * 1024 * 1024)
    response = client.post(
        "/api/scans", headers=officer,
        files={"image": ("huge.jpg", payload, "image/jpeg")},
    )
    assert response.status_code == 413
    assert "20 MB" in response.json()["detail"]


def test_an_oversized_catalogue_is_refused(client, officer):
    response = client.post(
        "/api/listings/import", headers=officer,
        files={"file": ("huge.csv", b"a" * (11 * 1024 * 1024), "text/csv")},
    )
    assert response.status_code == 413


def test_an_empty_upload_is_refused(client, officer):
    response = client.post(
        "/api/scans", headers=officer,
        files={"image": ("empty.jpg", b"", "image/jpeg")},
    )
    assert response.status_code == 400


# -- rate limiting -----------------------------------------------------------


def test_a_caller_cannot_loop_on_the_scan_endpoint(client, officer):
    """The scan endpoint costs seconds of CPU, so it gets a ceiling.

    Sent deliberately-invalid images: what is asserted is that the limiter
    engages before the work does, so the responses before the ceiling need only
    be "not 429".
    """
    seen_429 = False
    for _ in range(ratelimit.SCAN_LIMIT + 2):
        response = client.post(
            "/api/scans", headers=officer,
            files={"image": ("x.jpg", b"not really an image", "image/jpeg")},
        )
        if response.status_code == 429:
            seen_429 = True
            assert int(response.headers["Retry-After"]) > 0
            break

    assert seen_429, f"no 429 within {ratelimit.SCAN_LIMIT + 2} requests"


def test_reads_are_never_rate_limited(client):
    """The dashboard is a public showcase; browsing it is not abuse."""
    for _ in range(ratelimit.SCAN_LIMIT + 5):
        assert client.get("/api/analytics/summary").status_code == 200


# -- notice signatures -------------------------------------------------------


def test_a_signature_verifies_against_the_record_it_covers():
    fields = dict(
        reference="LM/2026/0001", scan_digest="a" * 64,
        officer_id="LMO-0007", signed_at=datetime.now(timezone.utc),
        body="Whereas an inspection was carried out...",
    )
    assert signing.verify(signing.sign(**fields), **fields)


@pytest.mark.parametrize("field,value", [
    ("officer_id", "LMO-0099"),
    ("reference", "LM/2026/0002"),
    ("scan_digest", "b" * 64),
    ("body", "Whereas an inspection was carried out, slightly altered."),
])
def test_altering_a_signed_notice_breaks_its_signature(field, value):
    """The point of signing it at all.

    A notice is the one artefact with legal consequence, and the interface has
    always said it has no effect until an officer signs. That is worth
    something only if a later edit is detectable.
    """
    fields = dict(
        reference="LM/2026/0001", scan_digest="a" * 64,
        officer_id="LMO-0007", signed_at=datetime.now(timezone.utc),
        body="Whereas an inspection was carried out...",
    )
    signature = signing.sign(**fields)
    assert not signing.verify(signature, **{**fields, field: value})


def test_an_unsigned_notice_does_not_verify():
    assert not signing.verify(None, reference="r", scan_digest="d",
                              officer_id="o", signed_at=datetime.now(timezone.utc), body="b")
