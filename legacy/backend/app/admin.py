"""Portal administration: who may use the Credit Portal, and in which role.

Only Portal Administrators may call these endpoints. Identities themselves are managed in the
identity provider (Entra ID); this module only grants, changes and deactivates PORTAL access.
Every change is written to the activity log with the administrator's identity.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import directory
from app.auth import PORTAL_ROLES, CurrentUser, admin_user
from app.db import ActivityLog, Analyst, AnalystPortfolio, CreditMemo, get_session

router = APIRouter(prefix="/api/admin", tags=["portal administration"])

ROLE_LABELS = {
    "analyst": "Credit Analyst",
    "credit_officer": "Credit Officer (approver)",
    "compliance": "Compliance Reviewer (read-only)",
    "admin": "Portal Administrator",
}


class GrantAccess(BaseModel):
    email: str
    role: str
    title: str | None = None


class UpdateUser(BaseModel):
    role: str | None = None
    active: bool | None = None
    title: str | None = None


def _check_role(role: str) -> None:
    if role not in PORTAL_ROLES:
        raise HTTPException(422, f"Unknown role '{role}'. Valid: {', '.join(PORTAL_ROLES)}")


def _log(s: Session, admin: CurrentUser, action: str) -> None:
    s.add(ActivityLog(at=datetime.now(), actor=admin.email, action=f"[admin] {action}"))


def _user_row(s: Session, a: Analyst) -> dict:
    return {
        "email": a.email, "name": a.name, "title": a.title, "role": a.role,
        "role_label": ROLE_LABELS.get(a.role, a.role), "active": a.active,
        "portfolio_size": s.scalar(select(func.count()).select_from(AnalystPortfolio)
                                   .where(AnalystPortfolio.analyst_email == a.email)),
        "open_memos": s.scalar(select(func.count()).select_from(CreditMemo)
                               .where(CreditMemo.analyst_email == a.email,
                                      CreditMemo.status.in_(("Draft", "Returned", "Submitted")))),
    }


@router.get("/roles")
def roles(admin: CurrentUser = Depends(admin_user)):
    return [{"role": r, "label": ROLE_LABELS[r]} for r in PORTAL_ROLES]


@router.get("/users")
def users(admin: CurrentUser = Depends(admin_user), s: Session = Depends(get_session)):
    return [_user_row(s, a) for a in s.scalars(select(Analyst).order_by(Analyst.name))]


@router.get("/directory")
def search_directory(q: str = "", admin: CurrentUser = Depends(admin_user),
                     s: Session = Depends(get_session)):
    """Employees in the identity provider, flagged with any existing portal access."""
    try:
        people = directory.search(q)
    except NotImplementedError as e:
        raise HTTPException(501, str(e)) from e
    accounts = {a.email: a for a in s.scalars(select(Analyst))}
    return [{**p, "has_access": p["email"] in accounts,
             "role": accounts[p["email"]].role if p["email"] in accounts else None,
             "active": accounts[p["email"]].active if p["email"] in accounts else None}
            for p in people]


@router.post("/users")
def grant_access(body: GrantAccess, admin: CurrentUser = Depends(admin_user),
                 s: Session = Depends(get_session)):
    _check_role(body.role)
    person = directory.lookup(body.email)
    if not person:
        raise HTTPException(404, f"{body.email} is not in the employee directory")
    if s.get(Analyst, person["email"]):
        raise HTTPException(409, f"{person['email']} already has portal access")
    account = Analyst(email=person["email"], name=person["name"],
                      title=body.title or person["job_title"], role=body.role, active=True)
    s.add(account)
    _log(s, admin, f"Granted {person['email']} portal access as {ROLE_LABELS[body.role]}")
    s.commit()
    return _user_row(s, account)


@router.patch("/users/{email}")
def update_user(email: str, body: UpdateUser, admin: CurrentUser = Depends(admin_user),
                s: Session = Depends(get_session)):
    account = s.get(Analyst, email.lower())
    if not account:
        raise HTTPException(404, f"{email} has no portal access")
    if account.email == admin.email and (
        (body.role is not None and body.role != account.role) or body.active is False
    ):
        raise HTTPException(409, "You cannot change your own role or deactivate yourself")
    changes = []
    if body.role is not None and body.role != account.role:
        _check_role(body.role)
        changes.append(f"role {ROLE_LABELS[account.role]} -> {ROLE_LABELS[body.role]}")
        account.role = body.role
    if body.active is not None and body.active != account.active:
        changes.append("reactivated" if body.active else "deactivated")
        account.active = body.active
    if body.title is not None and body.title.strip() and body.title != account.title:
        changes.append(f"title '{account.title}' -> '{body.title.strip()}'")
        account.title = body.title.strip()
    if changes:
        _log(s, admin, f"Updated {account.email}: {'; '.join(changes)}")
        s.commit()
    return _user_row(s, account)
