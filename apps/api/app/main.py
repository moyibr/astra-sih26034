"""ASTRA API.

Run it with::

    uvicorn app.main:app --reload --app-dir apps/api
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from astra_rules import RulePack

from .config import settings
from .db import init_db
from .routers import analytics, listings, rulepacks, scans
from .services import scanning

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("astra.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()

    pack = RulePack.load(settings.active_rulepack)
    log.info("rule pack %s loaded: %d rules", pack.identifier, len(pack.rules))
    pending = sum(1 for r in pack.rules if r.verification == "NEEDS_GAZETTE_CHECK")
    if pending:
        # Loud on purpose. These citations are not yet confirmed against the
        # gazette, and nobody should quote them in a hearing until they are.
        log.warning(
            "%d of %d rules are still marked NEEDS_GAZETTE_CHECK - see docs/rule-citations.md",
            pending, len(pack.rules),
        )

    if not scanning.scanning_available():
        # Said plainly at boot, because someone reading the logs of a browse-only
        # deployment should not have to work out why no scan ever succeeds.
        log.info(
            "live scanning is not available on this deployment; "
            "recorded inspections, analytics, the rule pack and e-commerce "
            "auditing are unaffected"
        )
    elif settings.warm_ocr_on_startup:
        # Paying the model-loading cost at boot keeps it out of the first scan,
        # which is invariably the one being demonstrated.
        try:
            import numpy as np

            from vision.pipeline import ocr

            ocr.read(np.zeros((64, 64, 3), dtype=np.uint8))
            log.info("OCR models warmed")
        except Exception:
            log.warning("could not warm OCR models; first scan will be slower", exc_info=True)

    yield


app = FastAPI(
    title="ASTRA",
    version="0.1.0",
    summary=(
        "Automated compliance checking for packaged commodities under the Legal "
        "Metrology (Packaged Commodities) Rules, 2011."
    ),
    description=(
        "ASTRA triages, measures and evidences. It does not issue legal notices: "
        "a notice drafted here has no effect until a named Legal Metrology Officer "
        "signs it."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scans.router)
app.include_router(listings.router)
app.include_router(analytics.router)
app.include_router(rulepacks.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness, and what this particular deployment can do.

    `scanning` is the one field worth reading: the frontend uses it to decide
    whether to offer the camera at all, so a browse-only deployment explains
    itself instead of presenting a form that will fail.
    """
    pack = RulePack.load(settings.active_rulepack)
    return {
        "status": "ok",
        "env": settings.env,
        "rulepack": pack.identifier,
        "rules": len(pack.rules),
        "scanning": scanning.scanning_available(),
    }
