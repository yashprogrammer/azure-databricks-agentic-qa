import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import seed

MARCUS, ANA, PRIYA = "m.lee@contoso.example", "a.ruiz@contoso.example", "p.raman@contoso.example"


@pytest.fixture(scope="module")
def client():
    seed(reset=True)
    with TestClient(app) as c:
        yield c


def auth(client, email: str) -> dict:
    r = client.post("/dev-idp/token", json={"username": email, "password": "contoso-dev"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_every_api_requires_a_token(client):
    assert client.get("/api/memos").status_code == 401
    assert client.get("/api/borrowers").status_code == 401


def test_wrong_password_and_tampered_tokens_are_rejected(client):
    bad = client.post("/dev-idp/token", json={"username": MARCUS, "password": "guess"})
    assert bad.status_code == 401
    token = auth(client, MARCUS)["Authorization"]
    assert client.get("/api/me", headers={"Authorization": token[:-4] + "AAAA"}).status_code == 401


def test_identity_comes_from_the_token(client):
    me = client.get("/api/me", headers=auth(client, MARCUS)).json()
    assert me["email"] == MARCUS and me["roles"] == ["Credit.Analyst"] and me["role"] == "analyst"
    assert client.get("/api/me", headers=auth(client, PRIYA)).json()["role"] == "credit_officer"


def test_memo_has_the_six_template_sections(client):
    memo = client.get("/api/memos/CM-2026-0101", headers=auth(client, MARCUS)).json()
    assert [s["section_type"] for s in memo["sections"]] == [
        "business_overview", "industry_competition", "financial_performance",
        "liquidity_debt", "key_risks", "legal_regulatory",
    ]


def test_analyst_cannot_edit_another_analysts_memo(client):
    r = client.put("/api/memos/CM-2026-0103/sections/key_risks",  # Ana's memo
                   json={"body": "x"}, headers=auth(client, MARCUS))
    assert r.status_code == 403


def test_only_credit_officers_approve(client):
    marcus, priya = auth(client, MARCUS), auth(client, PRIYA)
    ok = client.put("/api/memos/CM-2026-0102/sections/key_risks",
                    json={"body": "Supplier concentration."}, headers=marcus)
    assert ok.status_code == 200
    section = next(s for s in client.get("/api/memos/CM-2026-0102", headers=marcus).json()["sections"]
                   if s["section_type"] == "key_risks")
    assert section["updated_by"] == MARCUS  # attributed from the token, not the request
    assert client.post("/api/memos/CM-2026-0102/submit", headers=marcus).json()["status"] == "Submitted"
    assert client.post("/api/memos/CM-2026-0102/approve", headers=marcus).status_code == 403
    assert client.put("/api/memos/CM-2026-0102/sections/key_risks", json={"body": "edit"},
                      headers=marcus).status_code == 409  # locked once submitted
    approved = client.post("/api/memos/CM-2026-0102/approve", headers=priya).json()
    assert approved["status"] == "Approved"


def test_officer_cannot_prepare_memos(client):
    r = client.post("/api/memos", json={"borrower_id": "B-1003"}, headers=auth(client, PRIYA))
    assert r.status_code == 403


def test_analyst_creates_memos_only_for_own_portfolio(client):
    marcus = auth(client, MARCUS)
    assert client.post("/api/memos", json={"borrower_id": "B-1008"}, headers=marcus).status_code == 403
    memo_id = client.post("/api/memos", json={"borrower_id": "B-1003"}, headers=marcus).json()["memo_id"]
    memo = client.get(f"/api/memos/{memo_id}", headers=marcus).json()
    assert memo["analyst_email"] == MARCUS and len(memo["sections"]) == 6


def test_restricted_list_is_flagged_but_not_enforced(client):
    # Legacy behaviour (pain point P5): the restriction is only a warning flag.
    marcus = auth(client, MARCUS)
    tickers = {r["ticker"] for r in client.get("/api/restricted", headers=marcus).json()}
    assert tickers == {"TSLA", "META"}
    assert client.get("/api/borrowers/B-1020", headers=marcus).json()["restricted"] is True


def test_portfolio_is_the_signed_in_users(client):
    assert "B-1001" in client.get("/api/portfolio", headers=auth(client, MARCUS)).json()
    assert "B-1001" not in client.get("/api/portfolio", headers=auth(client, ANA)).json()
