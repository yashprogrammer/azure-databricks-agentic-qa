"""Employee directory lookup used by portal administration.

The portal never creates bank identities; it only grants portal access to employees who already
exist in the identity provider. Locally that is the development IdP's directory; on Azure it is
Microsoft Entra ID, queried through Microsoft Graph (GET /users, needs User.ReadBasic.All).
"""

from __future__ import annotations

import os

DEV_IDP_ENABLED = os.environ.get("DEV_IDP_ENABLED", "true").lower() == "true"


def search(q: str = "") -> list[dict]:
    """Returns [{"email", "name", "job_title"}] for employees matching `q`."""
    if DEV_IDP_ENABLED:
        from app.dev_idp import search_directory

        return search_directory(q)
    raise NotImplementedError("Directory search via Microsoft Graph is configured on Azure")


def lookup(email: str) -> dict | None:
    email = email.strip().lower()
    return next((e for e in search(email) if e["email"] == email), None)
