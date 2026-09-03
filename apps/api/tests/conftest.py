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


@pytest.fixture(scope="session")
def unmeasurable_but_defective_png() -> bytes:
    """A label with a real defect and no way to measure anything.

    The consumer-care block is stripped out, which is a violation any reader can
    see without a ruler, and no calibration card is in frame, so every
    millimetre rule is necessarily undecided. That combination is what a notice
    has to handle honestly: allege the defect, and say plainly which checks it
    is *not* alleging.
    """
    declarations = [
        d
        for d in synth.default_declarations()
        if "Customer Care" not in d.text
        and "Tel 1800" not in d.text
        and "@" not in d.text
    ]
    png, _ = synth.render(
        synth.LabelSpec(declarations=declarations, with_id1_card=False)
    )
    return png
