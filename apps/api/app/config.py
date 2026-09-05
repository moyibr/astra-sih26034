"""Runtime configuration.

Defaults are chosen so that ``uvicorn app.main:app`` works on a freshly cloned
repository with nothing else running -- SQLite on disk, images in a local
directory, no queue, no object store. Every one of those is swapped by an
environment variable for the container deployment, but a teammate should never
have to stand up Postgres to see the thing work.
"""

from __future__ import annotations

import pathlib

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def astra(name: str) -> AliasChoices:
    """Accept both ``ASTRA_THING`` and the bare ``THING``.

    Three settings were documented with an ``ASTRA_`` prefix in `.env.example`
    and set that way in `render.yaml`, but no `env_prefix` was ever configured,
    so pydantic-settings was looking for the bare names and silently kept its
    defaults. The deployed service reported `env=development` while its
    environment plainly said production, which is the sort of thing that is
    noticed late and by accident.

    Names without the prefix -- DATABASE_URL, PORT -- are conventions the
    hosting platform sets itself, so they stay bare.
    """
    return AliasChoices(f"ASTRA_{name.upper()}", name.upper())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = Field(default="development", validation_alias=astra("env"))
    secret_key: str = Field(
        default="change-me-in-production", validation_alias=astra("secret_key")
    )

    active_rulepack: str = Field(
        default="lmpc-2011@2026.07.01", validation_alias=astra("active_rulepack")
    )

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

    writes_enabled: bool = True
    """Whether this deployment accepts anything that changes state.

    The public instance sets this false. It exists to show recorded
    inspections and the rule pack, and nothing there should be alterable by
    whoever happens to open the link -- which, until officers were introduced,
    was anyone at all. Read-only by construction beats read-only by hoping the
    credential does not leak.
    """

    officers: str = Field(default="", validation_alias=astra("officers"))
    """Officers who may record decisions: `token:id:Name`, comma separated.

    Empty by default, so a fresh checkout cannot accidentally ship a working
    credential. Parsed in app/auth.py, which is also the seam a pilot would
    replace with the department's own directory.
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
