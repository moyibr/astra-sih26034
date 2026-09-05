"""Settings actually read the environment variables they are documented with.

This exists because three of them did not. `.env.example` documented
`ASTRA_ENV`, `ASTRA_SECRET_KEY` and `ASTRA_ACTIVE_RULEPACK`, and `render.yaml`
set all three, but no `env_prefix` was configured -- so pydantic-settings looked
for the bare names, found nothing, and quietly kept its defaults.

Nothing failed. The deployed service simply ran as `development` with a
placeholder secret while its environment plainly said otherwise, and the only
reason it came to light was a stray field in a health response.

A configuration setting that is silently ignored is worse than one that is
missing, so every documented name is asserted here.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.config import Settings

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "variable,field,value",
    [
        ("ASTRA_ENV", "env", "production"),
        ("ASTRA_SECRET_KEY", "secret_key", "not-the-default"),
        ("ASTRA_ACTIVE_RULEPACK", "active_rulepack", "lmpc-2011@2026.07.01"),
        ("SCANNING_ENABLED", "scanning_enabled", "false"),
        ("DATABASE_URL", "database_url", "sqlite:///tmp/x.db"),
        ("CORS_ORIGIN_REGEX", "cors_origin_regex", r"^https://x\.example$"),
        ("WARM_OCR_ON_STARTUP", "warm_ocr_on_startup", "false"),
    ],
)
def test_documented_environment_variables_are_read(monkeypatch, variable, field, value):
    monkeypatch.setenv(variable, value)
    settings = Settings()

    actual = getattr(settings, field)
    expected = {"false": False, "true": True}.get(value, value)
    assert str(actual).lower() == str(expected).lower(), (
        f"{variable} was set but {field} did not change; it is being ignored"
    )


def test_the_prefix_is_optional(monkeypatch):
    """Both spellings work, so neither documentation nor habit can be wrong."""
    monkeypatch.setenv("ENV", "staging")
    assert Settings().env == "staging"


def test_defaults_survive_an_empty_environment():
    settings = Settings()
    assert settings.env == "development"
    assert settings.scanning_enabled is True
    assert settings.active_rulepack == "lmpc-2011@2026.07.01"


def test_every_variable_in_render_yaml_maps_to_a_real_setting():
    """Guard the file that actually configures the deployment.

    A name in render.yaml that no setting reads looks like configuration and
    behaves like a comment. This catches the next one at test time rather than
    in a health response weeks later.
    """
    render = (REPO_ROOT / "render.yaml").read_text(encoding="utf-8")
    keys = set(re.findall(r"^\s*- key:\s*(\w+)\s*$", render, re.MULTILINE))

    # Set by the platform, not by us.
    platform_owned = {"PORT"}

    unread = set()
    for key in keys - platform_owned:
        probe = Settings(_env_file=None)
        before = {f: getattr(probe, f) for f in type(probe).model_fields}
        import os

        os.environ[key] = "__probe__"
        try:
            after = Settings(_env_file=None)
            changed = any(
                getattr(after, f) != before[f] for f in type(after).model_fields
            )
        except Exception:
            # A validation error means the value *was* read, just not coercible.
            changed = True
        finally:
            del os.environ[key]

        if not changed:
            unread.add(key)

    assert not unread, (
        f"render.yaml sets {sorted(unread)}, which no setting reads. "
        "Either the name is wrong or the setting is missing."
    )
