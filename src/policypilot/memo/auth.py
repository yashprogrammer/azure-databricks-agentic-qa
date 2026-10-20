"""Authentication for the AI Credit Memo Draft service.

The portal forwards the signed-in user's bearer token; this service validates it itself
(signature via the issuer's JWKS, issuer, audience, expiry) and takes the user's IDENTITY only
from it. The token carries no roles: the Credit Portal owns users and roles, so the service asks
the portal (GET /api/me, with the same token) for the user's role and whether their access is
active. The legacy system stays the single source of truth for who may do what.

Locally the issuer is the Credit Portal's development IdP; on Azure, Microsoft Entra ID:

    AUTH_ISSUER    https://login.microsoftonline.com/<tenant-id>/v2.0
    AUTH_AUDIENCE  api://<credit-portal-api-client-id>
    AUTH_JWKS_URL  https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import jwt

from policypilot.memo.legacy_client import LEGACY_API_URL

ANALYST = "Credit.Analyst"
OFFICER = "Credit.Officer"
COMPLIANCE = "Compliance.Reviewer"


@dataclass(frozen=True)
class CurrentUser:
    email: str
    name: str
    roles: frozenset[str]  # filled from the Credit Portal, not from the token
    token: str  # forwarded to the legacy API so it applies this user's permissions

    def has(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))


class TokenValidator:
    def __init__(
        self,
        issuer: str | None = None,
        audience: str | None = None,
        jwks_url: str | None = None,
        key=None,
    ):
        self.issuer = issuer or os.environ.get("AUTH_ISSUER", f"{LEGACY_API_URL}/dev-idp")
        self.audience = audience or os.environ.get("AUTH_AUDIENCE", "api://contoso-credit-portal")
        url = jwks_url or os.environ.get("AUTH_JWKS_URL", f"{self.issuer}/.well-known/jwks.json")
        self._key = key  # a fixed public key (tests); otherwise keys come from the JWKS
        self._jwks = None if key is not None else jwt.PyJWKClient(url, cache_keys=True)

    def validate(self, token: str) -> CurrentUser:
        """Raises jwt.PyJWTError if the token is not acceptable."""
        key = self._key if self._key is not None else self._jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["RS256"], audience=self.audience, issuer=self.issuer
        )
        email = str(claims.get("preferred_username") or claims.get("email") or "").lower()
        if not email:
            raise jwt.InvalidTokenError("token has no user name")
        return CurrentUser(
            email=email, name=str(claims.get("name") or email), roles=frozenset(), token=token
        )
