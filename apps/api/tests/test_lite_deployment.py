"""The browse-only deployment.

Three attempts to deploy this system failed before it became clear that the
free hosting tier provides a tenth of a CPU, on which a scan takes about a
minute and loading the OCR models at boot overruns a health check. The response
was to make the vision stack optional rather than mandatory: the API keeps every
surface that does not need to read a photograph, and declines the one that does.

These tests hold that boundary in place. The failure they guard against is
quiet — a stray module-level `import cv2` somewhere in the API would not break
anything locally, and would simply stop the public deployment from booting.
"""

from __future__ import annotations

import importlib

import pytest

from app.services import scanning


@pytest.fixture
def browse_only(monkeypatch):
    """Behave as the public deployment does: no live scanning offered."""
    monkeypatch.setattr(scanning.settings, "scanning_enabled", False)
    scanning.scanning_available.cache_clear()
    yield
    scanning.scanning_available.cache_clear()


def test_health_reports_whether_this_deployment_can_scan(client):
    body = client.get("/health").json()
    assert "scanning" in body
    assert isinstance(body["scanning"], bool)


def test_health_says_no_when_scanning_is_declined(client, browse_only):
    assert client.get("/health").json()["scanning"] is False


def test_scanning_is_declined_with_an_explanation_not_a_crash(
    client, browse_only, compliant_png
):
    """503, and a message that says where scanning does work.

    A 500 would suggest something is broken. Nothing is: this deployment simply
    does not offer the capability, and the caller deserves to be told which one
    does.
    """
    response = client.post(
        "/api/scans", files={"image": ("label.png", compliant_png, "image/png")}
    )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "locally" in detail
    assert "CPU" in detail


def test_everything_that_does_not_need_a_photograph_still_works(client, browse_only):
    """The point of the split: most of the system needs no computer vision."""
    assert client.get("/api/analytics/summary").status_code == 200
    assert client.get("/api/analytics/by-rule").status_code == 200
    assert client.get("/api/analytics/heatmap").status_code == 200
    assert client.get("/api/scans").status_code == 200
    assert client.get("/api/rulepacks/active").status_code == 200


def test_the_ecommerce_audit_works_without_the_vision_stack(client, browse_only):
    """Rule 6(10A) is a question about a platform's search, not about pixels.

    Reading declarations out of listing text needs regular expressions and the
    rule engine, and nothing heavier -- which is what lets the public deployment
    carry the newest and most distinctive check in the pack.
    """
    from vision.adapters import listing as adapter

    response = client.post(
        "/api/listings/import",
        files={"file": ("catalogue.csv", adapter.sample_csv().encode(), "text/csv")},
    )
    assert response.status_code == 201
    assert response.json()["platform_filter_violations"] == 2


def test_the_field_extractor_carries_no_computer_vision():
    """The import that must stay light.

    `vision.adapters.listing` is reachable from the API at import time. If it
    ever pulls in OpenCV, the lite image stops being lite and the deployment
    stops booting on a small instance.
    """
    module = importlib.import_module("vision.adapters.listing")
    source = importlib.import_module("vision.pipeline.extract")

    for name in ("cv2", "numpy", "onnxruntime", "rapidocr"):
        assert not hasattr(module, name), f"{name} leaked into the listing adapter"
        assert not hasattr(source, name), f"{name} leaked into the field extractor"


def test_the_api_does_not_import_the_vision_pipeline_at_module_scope():
    """Scanning is loaded on demand, inside run_scan, and nowhere else.

    Checked against the source rather than by importing, because on this machine
    the OCR stack *is* installed -- so the only way to catch the regression that
    matters is to look at where the import is written.
    """
    import pathlib

    service = pathlib.Path(scanning.__file__).read_text(encoding="utf-8")
    body = service.split("def run_scan(", 1)
    assert len(body) == 2, "run_scan not found"

    header, remainder = body
    assert "from vision.pipeline.analyse import analyse" not in header, (
        "the vision pipeline is imported at module scope again; that makes "
        "OpenCV and ONNX Runtime mandatory for the whole service"
    )
    assert "from vision.pipeline.analyse import analyse" in remainder
