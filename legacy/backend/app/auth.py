"""Authentication and authorization for the Credit Portal API.

Who the user is comes ONLY from a validated bearer token: never from a query parameter or a
request body. Locally the token is issued by the development IdP (app/dev_idp.py); on Azure by
Microsoft Entra ID. Only the issuer, audience and key source change:

    AUTH_ISSUER    https://login.microsoftonline.com/<tenant-id>/v2.0
    AUTH_AUDIENCE  api://<credit-portal-api-client-id>
    AUTH_JWKS_URL  https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import Analyst, get_session

AUTH_ISSUER = os.environ.get("AUTH_ISSUER", "http://localhost:8100/dev-idp")
AUTH_AUDIENCE = os.environ.get("AUTH_AUDIENCE", "api://contoso-credit-portal")
AUTH_JWKS_URL = os.environ.get("AUTH_JWKS_URL", "")  # empty: use the in-process dev IdP key

ANALYST = "Credit.Analyst"
OFFICER = "Credit.Officer"
COMPLIANCE = "Compliance.Reviewer"

_jwks_client = jwt.PyJWKClient(AUTH_JWKS_URL) if AUTH_JWKS_URL else None
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    email: str
    name: str
    title: str
    roles: frozenset[str]

    def has(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))

    @property
    def role(self) -> str:
        """Single display role for the UI (enforcement always uses `roles`)."""
        if OFFICER in self.roles:
            return "credit_officer"
        if COMPLIANCE in self.roles:
            return "compliance"
        return "analyst"


def _signing_key(token: str):
    if _jwks_client:
        return _jwks_client.get_signing_key_from_jwt(token).key
    from app.dev_idp import public_key

    return public_key()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    s: Session = Depends(get_session),
) -> CurrentUser:
    if not creds:
        raise _unauthorized("Sign-in required")
    try:
        claims = jwt.decode(creds.credentials, _signing_key(creds.credentials),
                            algorithms=["RS256"], audience=AUTH_AUDIENCE, issuer=AUTH_ISSUER)
    except jwt.PyJWTError as e:
        raise _unauthorized(f"Invalid or expired token: {e}") from e
    email = str(claims.get("preferred_username") or claims.get("email") or "").lower()
    profile = s.get(Analyst, email)
    if not profile:
        raise HTTPException(403, f"{email or 'User'} has no Credit Portal account")
    return CurrentUser(email=email, name=str(claims.get("name") or profile.name),
                       title=profile.title, roles=frozenset(claims.get("roles") or []))


def require_role(*roles: str):
    def check(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not user.has(*roles):
            raise HTTPException(403, f"Requires role: {' or '.join(roles)}")
        return user

    return check


# Ready-made role dependencies for endpoints.
analyst_user = require_role(ANALYST)
officer_user = require_role(OFFICER)
