"""A ceiling on how often one caller can ask for expensive work.

A scan costs seconds of CPU and a few hundred megabytes of OCR models. Left
open, that is an endpoint anyone can point a loop at, and on a small instance
one loop is enough to make the service useless for everybody else.

This is a fixed-window counter held in memory, which is the right size of
solution here and no larger: it is per-process, so it does not survive a
restart and would not coordinate across replicas. A pilot puts this at the
gateway. What it does buy is that casual abuse stops being free, without
adding a dependency or a Redis to the deployment.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import HTTPException, Request

log = logging.getLogger(__name__)

_hits: dict[str, list[float]] = defaultdict(list)

#: Generous for an inspector working through a shelf, restrictive for a loop.
SCAN_LIMIT = 20
WRITE_LIMIT = 60
WINDOW_SECONDS = 60.0

#: Stop the dict growing without bound on a long-lived process.
_MAX_TRACKED_CLIENTS = 4096


def _client(request: Request) -> str:
    """Best available identifier for the caller.

    Behind Render and Vercel the peer address is the proxy, so the forwarded
    header is what distinguishes callers. It is client-controlled and therefore
    spoofable -- which is acceptable for a courtesy limit and would not be for
    anything security-bearing.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit(request: Request, *, bucket: str, allowance: int) -> None:
    now = time.monotonic()
    key = f"{bucket}:{_client(request)}"

    recent = [t for t in _hits[key] if now - t < WINDOW_SECONDS]

    if len(recent) >= allowance:
        retry_after = int(WINDOW_SECONDS - (now - recent[0])) + 1
        _hits[key] = recent
        log.info("rate limit hit on %s", key)
        raise HTTPException(
            429,
            f"Too many requests. This deployment allows {allowance} per minute; "
            f"try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )

    recent.append(now)
    _hits[key] = recent

    if len(_hits) > _MAX_TRACKED_CLIENTS:
        for stale in [k for k, v in _hits.items() if not v or now - v[-1] > WINDOW_SECONDS]:
            del _hits[stale]


def limit_scans(request: Request) -> None:
    """Dependency for the scan endpoint, which is the expensive one."""
    limit(request, bucket="scan", allowance=SCAN_LIMIT)


def limit_writes(request: Request) -> None:
    """Dependency for the cheaper state-changing endpoints."""
    limit(request, bucket="write", allowance=WRITE_LIMIT)
