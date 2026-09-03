"""Bulk assessment of e-commerce listings.

The scale argument for the system lives here — one upload assesses a platform's
whole range — and so does its newest rule. Rule 6(10A), in force since
1 July 2026, asks whether the *platform* lets a consumer filter and sort by
country of origin. That is a question about search architecture, not about any
individual pack, and it cannot be answered by looking at a photograph.
"""

from __future__ import annotations

from vision.adapters import listing as adapter


def _import(client, csv_text: str, dry_run: bool = False) -> dict:
    response = client.post(
        f"/api/listings/import?dry_run={str(dry_run).lower()}",
        files={"file": ("catalogue.csv", csv_text.encode(), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_the_sample_catalogue_documents_the_expected_columns(client):
    body = client.get("/api/listings/sample").json()
    assert "listing_id" in body["columns"]
    assert "has_country_filter" in body["columns"]
    # Blank must mean "not assessed", never "absent".
    assert "not assessed" in body["notes"]


def test_a_catalogue_imports_and_is_assessed(client):
    result = _import(client, adapter.sample_csv())
    assert result["imported"] == 3
    assert result["non_compliant"] >= 2
    assert len(result["scan_ids"]) == 3


def test_a_dry_run_assesses_without_persisting(client):
    before = len(client.get("/api/scans", params={"limit": 500}).json())
    result = _import(client, adapter.sample_csv(), dry_run=True)
    after = len(client.get("/api/scans", params={"limit": 500}).json())

    assert result["imported"] == 3
    assert result["scan_ids"] == []
    assert after == before


def test_reimporting_the_same_catalogue_does_not_duplicate_listings(client):
    """A listing has a stable identity, so a re-run updates rather than piles up.

    A regulator re-checking a platform weekly must see one record per listing
    with the current verdict, not fifty-two rows to reconcile.
    """
    first = _import(client, adapter.sample_csv())
    second = _import(client, adapter.sample_csv())
    assert first["scan_ids"] == second["scan_ids"]


def test_a_compliant_listing_passes(client):
    """SKU-1001 declares everything and sits on a platform with a proper filter."""
    _import(client, adapter.sample_csv())
    listings = adapter.parse_csv(adapter.sample_csv())
    fields = adapter.to_fields(listings[0])

    scan = client.get(f"/api/scans/{fields.scan_id}").json()
    assert scan["critical_violations"] == 0


def test_the_2026_filter_rule_distinguishes_absent_from_unsortable(client):
    result = _import(client, adapter.sample_csv())
    # SKU-1002's filter is searchable but not sortable; SKU-1003 has none.
    assert result["platform_filter_violations"] == 2

    listings = adapter.parse_csv(adapter.sample_csv())
    unsortable = adapter.to_fields(listings[1])
    absent = adapter.to_fields(listings[2])

    def coo_finding(scan_id: str):
        scan = client.get(f"/api/scans/{scan_id}").json()
        return next(
            f for f in scan["report"]["findings"] if f["rule_id"] == "R6-10A-coo-filter"
        )

    assert coo_finding(unsortable.scan_id)["measured"] == "searchable only"
    assert coo_finding(absent.scan_id)["measured"] == "absent"


def test_a_domestic_listing_is_not_asked_for_a_country_filter(client):
    """The rule bites on imported goods. Indian products are not caught by it."""
    _import(client, adapter.sample_csv())
    fields = adapter.to_fields(adapter.parse_csv(adapter.sample_csv())[0])

    scan = client.get(f"/api/scans/{fields.scan_id}").json()
    finding = next(
        f for f in scan["report"]["findings"] if f["rule_id"] == "R6-10A-coo-filter"
    )
    assert finding["status"] == "NOT_APPLICABLE"


def test_a_listing_never_yields_a_millimetre_finding(client):
    """A listing page cannot tell you how tall the print on the pack is.

    Every height rule must come back undecided; guessing would be inventing
    evidence about a physical object nobody photographed.
    """
    _import(client, adapter.sample_csv())
    fields = adapter.to_fields(adapter.parse_csv(adapter.sample_csv())[1])

    scan = client.get(f"/api/scans/{fields.scan_id}").json()
    assert scan["calibration_source"] is None

    height_rules = [
        f
        for f in scan["report"]["findings"]
        if f["rule_id"] in {"R9-T1-netqty-height", "R9-letter-height"}
    ]
    assert height_rules
    assert all(f["status"] == "INDETERMINATE" for f in height_rules)


def test_an_unaudited_platform_is_not_recorded_as_failing(client):
    """Blank is not false. We have not looked, so we do not allege."""
    csv_text = (
        "listing_id,platform,brand,title,country_of_origin\n"
        "SKU-9001,unknown-platform,Some Brand,Imported Biscuits,Vietnam\n"
    )
    _import(client, csv_text)
    fields = adapter.to_fields(adapter.parse_csv(csv_text)[0])

    scan = client.get(f"/api/scans/{fields.scan_id}").json()
    finding = next(
        f for f in scan["report"]["findings"] if f["rule_id"] == "R6-10A-coo-filter"
    )
    assert finding["status"] == "INDETERMINATE"


def test_an_empty_or_malformed_upload_is_rejected(client):
    assert client.post(
        "/api/listings/import", files={"file": ("x.csv", b"", "text/csv")}
    ).status_code == 400

    assert client.post(
        "/api/listings/import",
        files={"file": ("x.csv", b"listing_id,brand\n", "text/csv")},
    ).status_code == 400


def test_unknown_columns_are_assessed_rather_than_discarded(client):
    """Platforms name their fields differently; an unanticipated declaration is
    still a declaration."""
    csv_text = (
        "listing_id,brand,title,seller_notes\n"
        'SKU-9002,Some Brand,Tea Powder,"Net Quantity: 250 g"\n'
    )
    listings = adapter.parse_csv(csv_text)
    fields = adapter.to_fields(listings[0])

    assert fields.net_quantity.present
    assert fields.net_quantity.value == 250
    assert fields.net_quantity.canonical_unit == "g"
