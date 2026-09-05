"""Runtime configuration.

Defaults are chosen so that ``uvicorn app.main:app`` works on a freshly cloned
repository with nothing else running -- SQLite on disk, images in a local
directory, no queue, no object store. Every one of those is swapped by an
environment variable for the container deployment, but a teammate should never
have to stand up Postgres to see the thing work.
"""

from __future__ import annotations

import pathlib

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"
    secret_key: str = "change-me-in-production"

    active_rulepack: str = "lmpc-2011@2026.07.01"

    database_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'astra.db').as_posix()}"
    upload_dir: pathlib.Path = REPO_ROOT / "data" / "uploads"
    demo_bundle_dir: pathlib.Path = REPO_ROOT / "data" / "demo"
    """Inspections and evidence committed to the repository.

    Copied into place when the database is empty, so a fresh container has
    something to show without ever running OCR during a build."""
    evidence_dir: pathlib.Path = REPO_ROOT / "data" / "evidence"

    #: Load the OCR models when the process starts rather than on the first
    #: scan. Costs a few seconds of boot and removes them from the demo.
    warm_ocr_on_startup: bool = True

    scanning_enabled: bool = True
    """Whether this deployment offers live scanning at all.

    Separate from whether the OCR stack happens to be installed, so a
    deployment can decline to scan even where it could. The public instance sets
    this false: on a tenth of a CPU a scan takes about a minute, and an endpoint
    that technically works but times out is worse than one that says plainly it
    is not offered here.
    """

    llm_normaliser_enabled: bool = False

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    cors_origin_regex: str | None = None
    """Pattern for origins that cannot be listed ahead of time.

    The deployed frontend's hostname is not known until Vercel has built it, and
    every preview branch gets its own. A regex covering the project's own
    deployments breaks that deadlock; it is deliberately not a wildcard.
    """

    def ensure_dirs(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        (REPO_ROOT / "data").mkdir(parents=True, exist_ok=True)


settings = Settings()
