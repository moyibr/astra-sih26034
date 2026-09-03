"""Pytest fixtures for the rule-engine suite.

The package builders live in ``label_fixtures`` rather than here. Two
conftest modules in one test run collide in ``sys.modules`` under the bare
name ``conftest``, so a test importing builders by that name silently picks up
whichever suite pytest loaded first.
"""

from __future__ import annotations

import pytest

from astra_rules import RulePack

from label_fixtures import PACK_ID


@pytest.fixture(scope="session")
def pack() -> RulePack:
    return RulePack.load(PACK_ID)
