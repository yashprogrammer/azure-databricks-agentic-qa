import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import seed
from tests.test_api import auth

ELENA, GRACE, ANA, DANIEL = (
    "e.novak@contoso.example", "g.kim@contoso.example",
    "a.ruiz@contoso.example", "d.cho@contoso.example",
)


@pytest.fixture()
def client():
    seed(reset=True)
    with TestClient(app) as c:
        yield c


def test_only_portal_admins_can_administer(client):
    assert client.get("/api/admin/users", headers=auth(client, ANA)).status_code == 403
    users = client.get("/api/admin/users", headers=auth(client, ELENA)).json()
    assert {u["email"] for u in users} >= {ELENA, ANA}


def test_directory_employee_needs_access_granted(client):
    grace = auth(client, GRACE)  # she can authenticate: she exists in the directory...
    assert client.get("/api/me", headers=grace).status_code == 403  # ...but has no portal access

    admin = auth(client, ELENA)
    found = client.get("/api/admin/directory", params={"q": "grace"}, headers=admin).json()
    assert found == [{"email": GRACE, "name": "Grace Kim", "job_title": "Credit Analyst",
                      "has_access": False, "role": None, "active": None}]

    granted = client.post("/api/admin/users", json={"email": GRACE, "role": "analyst"}, headers=admin)
    assert granted.status_code == 200 and granted.json()["active"] is True
    assert client.get("/api/me", headers=grace).json()["role"] == "analyst"  # same token works now
    again = client.post("/api/admin/users", json={"email": GRACE, "role": "analyst"}, headers=admin)
    assert again.status_code == 409


def test_role_change_applies_immediately_to_existing_tokens(client):
    ana, admin = auth(client, ANA), auth(client, ELENA)
    assert client.post("/api/memos", json={"borrower_id": "B-1008"}, headers=ana).status_code == 200
    client.patch(f"/api/admin/users/{ANA}", json={"role": "compliance"}, headers=admin)
    assert client.post("/api/memos", json={"borrower_id": "B-1008"}, headers=ana).status_code == 403


def test_deactivation_locks_the_user_out_until_reactivated(client):
    daniel, admin = auth(client, DANIEL), auth(client, ELENA)
    client.patch(f"/api/admin/users/{DANIEL}", json={"active": False}, headers=admin)
    assert client.get("/api/me", headers=daniel).status_code == 403
    client.patch(f"/api/admin/users/{DANIEL}", json={"active": True}, headers=admin)
    assert client.get("/api/me", headers=daniel).status_code == 200
    log = [a["action"] for a in client.get("/api/dashboard", headers=daniel).json()["activity"]]
    assert any("[admin] Updated d.cho@contoso.example: deactivated" in a for a in log)


def test_admin_cannot_lock_themselves_out_and_roles_are_validated(client):
    admin = auth(client, ELENA)
    assert client.patch(f"/api/admin/users/{ELENA}", json={"active": False}, headers=admin).status_code == 409
    assert client.patch(f"/api/admin/users/{ELENA}", json={"role": "analyst"}, headers=admin).status_code == 409
    bad = client.post("/api/admin/users", json={"email": GRACE, "role": "superuser"}, headers=admin)
    assert bad.status_code == 422
    nobody = client.post("/api/admin/users", json={"email": "x@evil.example", "role": "analyst"}, headers=admin)
    assert nobody.status_code == 404
