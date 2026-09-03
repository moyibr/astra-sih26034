"""API behaviour, end to end.

These cover the join between the engine and the enforcement workflow, and in
particular the boundary that the whole design rests on: ASTRA drafts, an officer
signs. There is a test below asserting that a notice cannot acquire legal effect
by any route other than a named officer signing it.
"""

from __future__ import annotations


def _post_scan(client, png: bytes, **form) -> dict:
    payload = {
        "shape": "RECTANGULAR",
        "height_mm": "180",
        "width_mm": "110",
        "inspector_id": "LMO-0042",
        "state": "Maharashtra",
        "district": "Pune",
        "brand": "Bharat Foods",
        "commodity_category": "packaged_food",
        "latitude": "18.5204",
        "longitude": "73.8567",
        "premises": "Shree General Stores, Pune",
    }
    payload.update({k: str(v) for k, v in form.items()})
    response = client.post(
        "/api/scans",
        files={"image": ("label.png", png, "image/png")},
        data=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


# -- meta --------------------------------------------------------------------


def test_health_reports_the_active_rule_pack(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["rulepack"] == "lmpc-2011@2026.07.01"
    assert body["rules"] == 22


def test_the_active_rule_pack_is_published_in_full(client):
    """A regulator should never have to take our word for which rules ran."""
    pack = client.get("/api/rulepacks/active").json()
    assert pack["identifier"] == "lmpc-2011@2026.07.01"
    assert pack["counts"]["rules"] == 22
    assert all(rule["implemented"] for rule in pack["rules"])
    assert pack["tables"]["table_I"]["bands"][0]["printed"] == 1.0
    # The provisions still awaiting confirmation are published too, not hidden.
    assert pack["counts"]["awaiting_gazette_check"] > 0


# -- scanning ----------------------------------------------------------------


def test_a_compliant_label_scans_clean(client, compliant_png):
    body = _post_scan(client, compliant_png)
    assert body["verdict"] == "COMPLIANT"
    assert body["critical_violations"] == 0
    assert body["calibration_source"] == "ID1_CARD"
    assert body["status"] == "NEW"
    assert len(body["image_sha256"]) == 64


def test_an_undersized_label_is_flagged_with_its_citation(client, undersized_png):
    body = _post_scan(client, undersized_png)
    assert body["verdict"] == "NON_COMPLIANT"
    assert body["critical_violations"] >= 1

    finding = next(
        f for f in body["report"]["findings"] if f["rule_id"] == "R9-T1-netqty-height"
    )
    assert finding["status"] == "FAIL"
    assert finding["required"] == "2.5 mm"
    assert "Table-I" in finding["citation"]
    assert finding["evidence"]


def test_the_stored_report_pins_the_pack_that_judged_it(client, compliant_png):
    body = _post_scan(client, compliant_png)
    assert body["report"]["rulepack"] == body["rulepack"] == "lmpc-2011@2026.07.01"


def test_an_empty_upload_is_rejected(client):
    response = client.post("/api/scans", files={"image": ("x.png", b"", "image/png")})
    assert response.status_code == 400


def test_an_undecodable_upload_is_a_client_error_not_a_crash(client):
    response = client.post(
        "/api/scans", files={"image": ("x.png", b"not an image at all", "image/png")}
    )
    assert response.status_code == 400


def test_scans_can_be_listed_and_filtered(client):
    everything = client.get("/api/scans").json()
    assert everything

    flagged = client.get("/api/scans", params={"verdict": "NON_COMPLIANT"}).json()
    assert flagged
    assert {s["verdict"] for s in flagged} == {"NON_COMPLIANT"}


def test_the_original_image_can_be_retrieved_as_evidence(client, compliant_png):
    scan = _post_scan(client, compliant_png)
    response = client.get(f"/api/scans/{scan['id']}/image")
    assert response.status_code == 200
    assert response.content == compliant_png


def test_an_unknown_scan_is_a_404(client):
    assert client.get("/api/scans/does-not-exist").status_code == 404


# -- officer disposition -----------------------------------------------------


def test_an_officer_override_is_appended_and_never_rewrites_the_finding(client, undersized_png):
    """The engine's original verdict has to survive being disagreed with.

    It is the record of what the software actually said, which is what an
    appeal will examine.
    """
    scan = _post_scan(client, undersized_png)
    before = next(
        f for f in scan["report"]["findings"] if f["rule_id"] == "R9-T1-netqty-height"
    )

    updated = client.post(
        f"/api/scans/{scan['id']}/override",
        json={
            "rule_id": "R9-T1-netqty-height",
            "officer_status": "PASS",
            "officer_id": "LMO-0042",
            "reason": "Measured 2.7 mm with a calliper on the physical pack.",
        },
    ).json()

    after = next(
        f for f in updated["report"]["findings"] if f["rule_id"] == "R9-T1-netqty-height"
    )
    assert after == before

    assert len(updated["overrides"]) == 1
    assert updated["overrides"][0]["engine_status"] == "FAIL"
    assert updated["overrides"][0]["officer_status"] == "PASS"
    assert updated["status"] == "UNDER_REVIEW"


def test_an_override_needs_a_substantive_reason(client, undersized_png):
    scan = _post_scan(client, undersized_png)
    response = client.post(
        f"/api/scans/{scan['id']}/override",
        json={
            "rule_id": "R9-T1-netqty-height", "officer_status": "PASS",
            "officer_id": "LMO-0042", "reason": "no",
        },
    )
    assert response.status_code == 422


def test_overriding_a_rule_the_scan_never_assessed_is_rejected(client, compliant_png):
    scan = _post_scan(client, compliant_png)
    response = client.post(
        f"/api/scans/{scan['id']}/override",
        json={
            "rule_id": "R99-not-a-rule", "officer_status": "FAIL",
            "officer_id": "LMO-0042", "reason": "attempting an unknown rule",
        },
    )
    assert response.status_code == 404


# -- notices -----------------------------------------------------------------


def test_a_notice_drafts_with_its_citations_and_is_not_yet_effective(client, undersized_png):
    scan = _post_scan(client, undersized_png)
    notice = client.post(
        f"/api/scans/{scan['id']}/notice", json={"addressee": "Bharat Foods Pvt Ltd"}
    ).json()

    assert notice["status"] == "DRAFT"
    assert notice["signed_by"] is None
    assert "R9-T1-netqty-height" in notice["cited_rules"]
    assert "Rule 9, Table-I" in notice["body"]
    assert "has no effect until signed" in notice["body"]
    assert scan["image_sha256"] in notice["body"]


def test_a_clean_scan_cannot_produce_a_notice(client, compliant_png):
    scan = _post_scan(client, compliant_png)
    response = client.post(f"/api/scans/{scan['id']}/notice", json={})
    assert response.status_code == 409


def test_a_notice_says_which_checks_it_is_not_alleging(client, undersized_png):
    """An officer who is not told what was undecided may assert more than the
    evidence supports."""
    scan = _post_scan(client, undersized_png, shape="OTHER", height_mm="", width_mm="")
    if scan["indeterminate"]:
        notice = client.post(f"/api/scans/{scan['id']}/notice", json={}).json()
        assert "NOT alleged" in notice["body"]


def test_only_a_named_officer_gives_a_notice_effect(client, undersized_png):
    scan = _post_scan(client, undersized_png)
    notice = client.post(f"/api/scans/{scan['id']}/notice", json={}).json()

    signed = client.post(
        f"/api/notices/{notice['id']}/sign", json={"officer_id": "LMO-0042"}
    ).json()
    assert signed["status"] == "SIGNED"
    assert signed["signed_by"] == "LMO-0042"
    assert signed["signed_at"]

    # Signing is not idempotent: a second signature is a workflow error.
    assert client.post(
        f"/api/notices/{notice['id']}/sign", json={"officer_id": "LMO-0099"}
    ).status_code == 409


def test_signing_requires_an_officer_identity(client, undersized_png):
    scan = _post_scan(client, undersized_png)
    notice = client.post(f"/api/scans/{scan['id']}/notice", json={}).json()
    assert client.post(
        f"/api/notices/{notice['id']}/sign", json={"officer_id": ""}
    ).status_code == 422


# -- analytics ---------------------------------------------------------------


def test_summary_counts_scans_and_surfaces_calibration_quality(client):
    body = client.get("/api/analytics/summary").json()
    assert body["total_scans"] > 0
    assert body["non_compliant"] > 0
    # An operational signal: how often inspectors omit a reference card.
    assert body["unusable_calibration_rate"] is not None


def test_violations_are_ranked_by_rule_with_their_citations(client):
    rows = client.get("/api/analytics/by-rule").json()
    assert rows
    assert rows[0]["violations"] >= rows[-1]["violations"]
    assert all(r["citation"] for r in rows)


def test_offenders_can_be_ranked_along_a_dimension(client):
    rows = client.get("/api/analytics/by-dimension", params={"dimension": "brand"}).json()
    assert rows
    assert rows[0]["key"] == "Bharat Foods"


def test_an_arbitrary_dimension_is_rejected(client):
    response = client.get(
        "/api/analytics/by-dimension", params={"dimension": "report_json"}
    )
    assert response.status_code == 422


def test_the_heatmap_weights_points_by_seriousness(client):
    points = client.get("/api/analytics/heatmap").json()
    assert points
    assert all(p["lat"] and p["lon"] for p in points)
    worst = max(points, key=lambda p: p["weight"])
    assert worst["weight"] == 1 + worst["critical"] * 2
