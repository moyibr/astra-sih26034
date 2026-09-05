"""Who is making this request.

The system's whole claim is that a finding is defensible and that every human
decision is recorded against the person who made it. Until now the officer's
identity arrived as a string in the request body, which means the audit trail
recorded whatever the caller typed -- and anyone could sign a notice in anyone
else's name. An identity the caller chooses is not an identity.

So identity comes from a bearer token and only from a bearer token. Routes that
change state depend on `require_officer`; reads stay open, because the
dashboard is meant to be linkable.

The registry is deliberately small. A pilot would put officers behind the
department's own directory, and the shape here -- resolve a credential, get an
officer -- is the same shape that would plug into it.
"""

from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from .config import settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Officer:
    """The person a request is acting as."""

    id: str
    name: str


def _registry() -> dict[str, Officer]:
    """Parse ASTRA_OFFICERS into token -> officer.

    Format: ``token:officer_id:Full Name``, entries separated by commas. Blank
    or malformed entries are skipped with a warning rather than crashing the
    process -- a typo in one officer's entry should not take the service down
    for the rest.
    """
    registry: dict[str, Officer] = {}
    for entry in settings.officers.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":", 2)
        if len(parts) != 3 or not all(p.strip() for p in parts):
            log.warning("ignoring malformed ASTRA_OFFICERS entry (expected token:id:name)")
            continue
        token, officer_id, name = (p.strip() for p in parts)
        registry[token] = Officer(id=officer_id, name=name)
    return registry


def _match(token: str) -> Officer | None:
    """Find the officer for a token, comparing in constant time.

    A plain dict lookup leaks token length and prefix through timing. The
    registry is small enough that comparing against every entry costs nothing.
    """
    found: Officer | None = None
    for candidate, officer in _registry().items():
        if hmac.compare_digest(candidate, token):
            found = officer
    return found


def require_officer(
    authorization: Annotated[str | None, Header()] = None,
) -> Officer:
    """Resolve the officer behind this request, or refuse it.

    Three refusals, each saying something different:

    * 403 when the deployment does not accept writes at all. The public
      instance is a showcase and is read-only by construction, so a leaked
      token still cannot change anything there.
    * 503 when writes are enabled but no officer has been configured, which is
      a deployment mistake rather than the caller's fault.
    * 401 when the credential is missing or unknown.
    """
    if not settings.writes_enabled:
        raise HTTPException(
            403,
            "This deployment is read-only. It publishes recorded inspections "
            "and the rule pack; recording an override or drafting a notice is "
            "done on a departmental instance.",
        )

    registry = _registry()
    if not registry:
        raise HTTPException(
            503,
            "No officers are configured on this deployment, so no one can be "
            "authenticated. Set ASTRA_OFFICERS as token:id:name entries.",
        )

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            401,
            "This action is recorded against a named officer, so it needs one. "
            "Send an officer token as `Authorization: Bearer <token>`.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    officer = _match(token.strip())
    if officer is None:
        raise HTTPException(
            401,
            "That officer token was not recognised.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    log.info("authenticated %s (%s)", officer.id, officer.name)
    return officer


CurrentOfficer = Annotated[Officer, Depends(require_officer)]
