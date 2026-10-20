"""DEVELOPMENT identity provider: a stand-in for Microsoft Entra ID when running locally.

It plays the bank's employee directory: it knows every employee, but NOT what they may do in
the Credit Portal (that is the portal's own user administration). It is a separate system from
the portal, mounted here only for local convenience and only when DEV_IDP_ENABLED=true.

It issues RS256-signed JWTs with the identity claims Entra ID puts in an access token (iss, aud,
oid, preferred_username, name) and publishes its public key as a JWKS, so the APIs validate
tokens exactly as they will validate Entra ID tokens on Azure. Never enable it in production.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, HTTPException
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel

from app.config import BACKEND_DIR

ISSUER = os.environ.get("AUTH_ISSUER", "http://localhost:8100/dev-idp")
AUDIENCE = os.environ.get("AUTH_AUDIENCE", "api://contoso-credit-portal")
# Shared development password for the fictional test accounts (see legacy/README.md).
DEV_PASSWORD = os.environ.get("DEV_IDP_PASSWORD", "contoso-dev")
TOKEN_LIFETIME = timedelta(hours=8)
KEY_ID = "contoso-dev-idp-1"
_KEY_PATH = BACKEND_DIR / "data" / "dev_idp_key.pem"

# The bank's employee directory (in Entra ID: the tenant's users). Some employees have no
# Credit Portal access until a portal administrator grants it. (name, job title)
DIRECTORY = {
    "m.lee@contoso.example": ("Marcus Lee", "Lead Credit Analyst"),
    "a.ruiz@contoso.example": ("Ana Ruiz", "Credit Analyst"),
    "d.cho@contoso.example": ("Daniel Cho", "Credit Analyst"),
    "p.raman@contoso.example": ("Priya Raman", "Chief Credit Officer"),
    "a.karim@contoso.example": ("Aisha Karim", "Compliance Officer"),
    "e.novak@contoso.example": ("Elena Novak", "Credit Portal Application Owner"),
    "g.kim@contoso.example": ("Grace Kim", "Credit Analyst"),
    "j.blake@contoso.example": ("Jordan Blake", "Model Risk Management Lead"),
    "s.okafor@contoso.example": ("Sam Okafor", "Data Platform Lead"),
    "t.fischer@contoso.example": ("Tom Fischer", "Information Security Engineer"),
}


def search_directory(q: str = "") -> list[dict]:
    """Employee lookup (on Azure: Microsoft Graph /users)."""
    q = q.strip().lower()
    return [{"email": e, "name": n, "job_title": t} for e, (n, t) in sorted(DIRECTORY.items())
            if not q or q in e or q in n.lower() or q in t.lower()]


def _private_key() -> rsa.RSAPrivateKey:
    """Persisted so tokens survive a restart of the local server."""
    if _KEY_PATH.exists():
        return serialization.load_pem_private_key(_KEY_PATH.read_bytes(), password=None)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _KEY_PATH.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    return key


_KEY = _private_key()


def public_key():
    return _KEY.public_key()


def issue_token(email: str) -> str:
    name, _title = DIRECTORY[email]
    now = datetime.now(UTC)
    oid = str(uuid.uuid5(uuid.NAMESPACE_DNS, email))
    claims = {  # identity only: what the user may do is decided by the Credit Portal
        "iss": ISSUER, "aud": AUDIENCE, "sub": oid, "oid": oid,
        "preferred_username": email, "name": name,
        "iat": now, "nbf": now, "exp": now + TOKEN_LIFETIME,
    }
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": KEY_ID})


router = APIRouter(prefix="/dev-idp", tags=["development identity provider"])


class TokenRequest(BaseModel):
    username: str
    password: str


@router.post("/token")
def token(body: TokenRequest):
    email = body.username.strip().lower()
    if email not in DIRECTORY or body.password != DEV_PASSWORD:
        raise HTTPException(401, "Invalid username or password")
    return {"access_token": issue_token(email), "token_type": "Bearer",
            "expires_in": int(TOKEN_LIFETIME.total_seconds())}


@router.get("/.well-known/openid-configuration")
def openid_configuration():
    return {"issuer": ISSUER, "token_endpoint": f"{ISSUER}/token",
            "jwks_uri": f"{ISSUER}/.well-known/jwks.json",
            "id_token_signing_alg_values_supported": ["RS256"]}


@router.get("/.well-known/jwks.json")
def jwks():
    jwk = RSAAlgorithm.to_jwk(public_key(), as_dict=True)
    return {"keys": [{**jwk, "kid": KEY_ID, "use": "sig", "alg": "RS256"}]}
