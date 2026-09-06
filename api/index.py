"""Vercel entrypoint for the public API.

The API and the frontend now live on one platform. They were split because the
API was 273 MB against Vercel's function limit -- OpenCV, ONNX Runtime and three
OCR models. Removing the OCR stack for the public deployment took it to 38 MB,
and at that size the reason for the split is gone, along with a Render instance
that slept for minutes at a time and the scheduled ping that existed to stop it.

The filesystem here is read-only apart from /tmp, which suits a deployment that
accepts no writes: the committed demo bundle unpacks into /tmp on a cold start
and nothing is lost when the instance is recycled.

If the real application cannot be imported, this serves a diagnostic instead of
crashing. A serverless function that fails to import returns nothing but
FUNCTION_INVOCATION_FAILED, and the logs are not always reachable -- so the one
thing worth guaranteeing is that the failure explains itself over HTTP.
"""

from __future__ import annotations

import os
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The workspace packages are not pip-installed here -- requirements.txt carries
# only third-party dependencies -- so they are imported from the source tree.
for package in ("apps/api", "packages/schema", "packages/rulepacks", "apps/vision"):
    sys.path.insert(0, str(ROOT / package))

# Everything writable has to live under /tmp.
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/astra/astra.db")
os.environ.setdefault("UPLOAD_DIR", "/tmp/astra/uploads")
os.environ.setdefault("EVIDENCE_DIR", "/tmp/astra/evidence")
os.environ.setdefault("DEMO_BUNDLE_DIR", str(ROOT / "data" / "demo"))

# This deployment reads and does not decide. Both are enforced in the
# application; these make the intent explicit at the edge.
os.environ.setdefault("SCANNING_ENABLED", "false")
os.environ.setdefault("WRITES_ENABLED", "false")
os.environ.setdefault("WARM_OCR_ON_STARTUP", "false")
os.environ.setdefault("ASTRA_ENV", "production")

try:
    from app.main import app
except Exception:  # noqa: BLE001 - the point is to report anything at all
    _failure = traceback.format_exc()

    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="ASTRA (failed to start)")

    def _tree(path: pathlib.Path, depth: int = 2) -> object:
        """What actually made it into the bundle.

        Nearly every way this import fails comes down to a file the deployment
        did not carry, and the fastest way to tell is to look.
        """
        if depth <= 0 or not path.is_dir():
            return "..." if path.is_dir() else path.name
        try:
            return {c.name: _tree(c, depth - 1) for c in sorted(path.iterdir())[:40]}
        except OSError as exc:
            return f"<unreadable: {exc}>"

    @app.get("/{full_path:path}")
    def _diagnose(full_path: str) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "status": "the API could not start",
                "traceback": _failure.splitlines(),
                "python": sys.version,
                "cwd": os.getcwd(),
                "root": str(ROOT),
                "sys_path_head": sys.path[:6],
                "bundle": _tree(ROOT),
            },
        )

__all__ = ["app"]
