"""Who a decision is recorded against.

The system's claim is that every human decision is attributable. Before these
tests existed, `officer_id` was a string in the request body: anyone could
overturn a finding or sign a legal notice in any officer's name, on a public
URL, with no credential at all. The two action buttons were live on the
internet.

The property worth protecting is narrow and absolute -- **a request cannot
choose its own identity** -- so it is asserted directly rather than inferred
from a 401 somewhere.
"""

from __future__ import annotations

import pytest

from app import auth
from app.config import settings

TOKEN = "test-token-value"
OTHER = "second-token-value"


@pytest.fixture
def officers(monkeypatch):
    monkeypatch.setattr(settings, "writes_enabled", True)
    monkeypatch.setattr(
        settings, "officers",
        f"{TOKEN}:LMO-0007:Anita Rao,{OTHER}:LMO-0099:Vikram Shah",
    )
    yield {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def read_only(monkeypatch):
    monkeypatch.setattr(settings, "writes_enabled", False)


def _a_scan(client) -> str:
    scans = client.get("/api/scans?limit=1").json()
    assert scans, "the fixture database has no scans to act on"
    return scans[0]["id"]


# -- the deployment can decline to be written to at all ----------------------


def test_a_read_only_deployment_refuses_writes(client, read_only):
    """403, and an explanation of where the action does belong.

    The public instance is a showcase. Read-only by construction means a leaked
    token still cannot change anything there.
    """
    response = client.post(
        f"/api/scans/{_a_scan(client)}/status?status=CONFIRMED",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 403
    assert "read-only" in response.json()["detail"].lower()


def test_reads_are_unaffected_by_read_only(client, read_only):
    assert client.get("/api/scans").status_code == 200
    assert client.get("/api/analytics/summary").status_code == 200
    assert client.get("/api/rulepacks/active").status_code == 200


def test_health_reports_whether_writes_are_accepted(client, read_only):
    assert client.get("/health").json()["writes"] is False


# -- a credential is required ------------------------------------------------


def test_an_unauthenticated_override_is_refused(client, officers):
    response = client.post(
        f"/api/scans/{_a_scan(client)}/override",
        json={"rule_id": "R9-T1-netqty-height", "officer_status": "PASS",
              "reason": "measured by hand at the premises"},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_an_unknown_token_is_refused(client, officers):
    response = client.post(
        f"/api/scans/{_a_scan(client)}/status?status=CONFIRMED",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


def test_signing_a_notice_requires_an_officer(client, officers):
    """The endpoint that gives a notice legal effect.

    Only a Legal Metrology Officer may issue one, so this is the request that
    must never succeed anonymously.
    """
    assert client.post("/api/notices/whatever/sign", json={}).status_code == 401


# -- and the identity comes from the credential, not the request -------------


def test_an_override_is_recorded_against_the_token_holder(client, officers):
    scan_id = _a_scan(client)
    findings = client.get(f"/api/scans/{scan_id}").json()["report"]["findings"]
    rule_id = next(f["rule_id"] for f in findings)

    response = client.post(
        f"/api/scans/{scan_id}/override",
        headers=officers,
        json={"rule_id": rule_id, "officer_status": "PASS",
              "reason": "measured by hand at the premises"},
    )
    assert response.status_code == 200
    assert response.json()["overrides"][-1]["officer_id"] == "LMO-0007"


def test_a_request_cannot_choose_its_own_identity(client, officers):
    """The whole point.

    A body claiming to be someone else must not change what is recorded. The
    field is gone from the schema, so this asserts both that the claim is
    ignored and that the token's officer is what lands in the audit trail.
    """
    scan_id = _a_scan(client)
    findings = client.get(f"/api/scans/{scan_id}").json()["report"]["findings"]
    rule_id = next(f["rule_id"] for f in findings)

    response = client.post(
        f"/api/scans/{scan_id}/override",
        headers=officers,
        json={"rule_id": rule_id, "officer_status": "PASS",
              "reason": "attempting to impersonate another officer",
              "officer_id": "LMO-0099"},
    )
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        assert response.json()["overrides"][-1]["officer_id"] == "LMO-0007"


def test_a_deployment_with_no_officers_says_so(client, monkeypatch):
    """503 rather than 401: nobody could authenticate, and that is our fault."""
    monkeypatch.setattr(settings, "writes_enabled", True)
    monkeypatch.setattr(settings, "officers", "")
    response = client.post(
        f"/api/scans/{_a_scan(client)}/status?status=CONFIRMED",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 503


# -- the registry itself -----------------------------------------------------


def test_malformed_registry_entries_are_skipped_not_fatal(monkeypatch):
    """One officer's typo must not take the service down for the rest."""
    monkeypatch.setattr(settings, "officers", f"nonsense,,{TOKEN}:LMO-0007:Anita Rao,a:b")
    registry = auth._registry()
    assert list(registry) == [TOKEN]
    assert registry[TOKEN].id == "LMO-0007"
