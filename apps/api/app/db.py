"""Database engine and session handling."""

from __future__ import annotations

import logging
import pathlib
import shutil
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base

log = logging.getLogger(__name__)

_is_sqlite = settings.database_url.startswith("sqlite")

engine: Engine = create_engine(
    settings.database_url,
    # SQLite's default single-thread check fights FastAPI's threadpool. The
    # database is only a development convenience; Postgres needs neither line.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        # WAL lets the dashboard read while a scan is being written, which is
        # otherwise a lock error the moment two people use the demo at once.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _install_demo_bundle() -> bool:
    """Seed an empty database from the dataset committed to the repository.

    Only ever runs when there is no database yet, so it cannot overwrite real
    inspections. The images are copied alongside the records deliberately: a
    database that outlived its evidence would leave every finding pointing at a
    photograph that no longer exists, which is worse than starting empty.

    This is what replaced generating the dataset during a container build. That
    put OpenCV, ONNX Runtime and a minute of OCR on the critical path of every
    deployment, and had to be redone on every restart of a host without a
    persistent disk.
    """
    bundle = settings.demo_bundle_dir
    bundle_db = bundle / "astra.db"
    if not bundle_db.exists():
        return False

    target = _sqlite_path()
    if target is None or target.exists():
        return False

    settings.ensure_dirs()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(bundle_db, target)

    copied = 0
    for image in (bundle / "uploads").glob("*"):
        if image.is_file():
            shutil.copy2(image, settings.upload_dir / image.name)
            copied += 1

    log.info("seeded from the committed demo bundle: %d evidence images", copied)
    return True


def _sqlite_path() -> pathlib.Path | None:
    """Filesystem path behind a SQLite URL, or None for any other database."""
    if not _is_sqlite:
        return None
    raw = settings.database_url.split("///", 1)[-1]
    return pathlib.Path(raw) if raw else None


def _add_missing_columns() -> None:
    """Bring an existing SQLite database up to the current model.

    `create_all` creates missing tables and nothing else, so adding a column to
    a model leaves every database that already exists -- including the demo
    bundle committed to the repository -- failing on the next query with `no
    such column`. That is precisely how the signature column broke the test
    suite, and it would have broken the deployment the same way.

    Additive only, and deliberately so. Adding a nullable column is safe to
    apply repeatedly and cannot lose data; anything that drops or rewrites is
    a migration tool's job, and the moment this project needs one it should
    take Alembic rather than grow this function.
    """
    if not _is_sqlite:
        return

    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            existing = {
                row[1]
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table.name})")
            }
            if not existing:
                continue  # create_all will make it
            for column in table.columns:
                if column.name in existing or not column.nullable:
                    continue
                type_sql = column.type.compile(engine.dialect)
                connection.exec_driver_sql(
                    f"ALTER TABLE {table.name} ADD COLUMN {column.name} {type_sql}"
                )
                log.info("added missing column %s.%s", table.name, column.name)


def init_db() -> None:
    settings.ensure_dirs()
    _install_demo_bundle()
    Base.metadata.create_all(engine)
    _add_missing_columns()


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
