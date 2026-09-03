"""Test harness for the API.

The environment is set before ``app.config`` is imported, because settings are
read once at import time. Each run gets its own SQLite file so tests never see
another run's scans.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

_tmp = pathlib.Path(tempfile.mkdtemp(prefix="astra-api-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(_tmp / "uploads")
os.environ["EVIDENCE_DIR"] = str(_tmp / "evidence")
# Model warm-up is a boot-time convenience, not behaviour under test.
os.environ["WARM_OCR_ON_STARTUP"] = "false"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "ml" / "eval"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import synth  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def compliant_png() -> bytes:
    png, _ = synth.compliant_label()
    return png


@pytest.fixture(scope="session")
def undersized_png() -> bytes:
    png, _ = synth.undersized_label()
    return png


@pytest.fixture(scope="session")
def label_truth() -> dict:
    _, truth = synth.compliant_label()
    return truth
