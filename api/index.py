"""Vercel entrypoint for the public API.

The API and the frontend now live on one platform, which is the point.

They were split across Vercel and Render because the API was 273 MB against
Vercel's function limit -- OpenCV, ONNX Runtime and three OCR models. Removing
the OCR stack for the public deployment took it to 38 MB, and at that size the
reason for the split is gone.

What goes with it: a free Render instance that slept after fifteen minutes and
took up to eight minutes to wake, the scheduled workflow that existed only to
stop it sleeping, and a CORS configuration between two origins. A Vercel
function does not sleep; a cold start is a few hundred milliseconds.

The filesystem here is read-only apart from /tmp, so the database and evidence
images are unpacked there from the bundle committed to the repository. That
suits this deployment exactly: it accepts no writes, so nothing is lost when
the instance is recycled and /tmp goes with it.
"""

from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The workspace packages are not pip-installed here -- requirements.txt carries
# only third-party dependencies -- so they are imported from the source tree.
for package in ("apps/api", "packages/schema", "packages/rulepacks", "apps/vision"):
    sys.path.insert(0, str(ROOT / package))

# Everything writable has to live under /tmp. `init_db` copies the committed
# demo bundle into these paths on a cold start, which is a few dozen files and
# costs milliseconds.
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/astra/astra.db")
os.environ.setdefault("UPLOAD_DIR", "/tmp/astra/uploads")
os.environ.setdefault("EVIDENCE_DIR", "/tmp/astra/evidence")
os.environ.setdefault("DEMO_BUNDLE_DIR", str(ROOT / "data" / "demo"))

# The public deployment reads and does not decide. Both are enforced in the
# application rather than assumed here; these make the intent explicit.
os.environ.setdefault("SCANNING_ENABLED", "false")
os.environ.setdefault("WRITES_ENABLED", "false")
os.environ.setdefault("WARM_OCR_ON_STARTUP", "false")
os.environ.setdefault("ASTRA_ENV", "production")

from app.main import app  # noqa: E402

# Vercel's Python runtime looks for an ASGI application named `app`.
__all__ = ["app"]
