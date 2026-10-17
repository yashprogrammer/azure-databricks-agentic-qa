import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import seed


@pytest.fixture(scope="module")
def client():
    seed(reset=True)
    with TestClient(app) as c:
        yield c


def test_memo_has_the_six_template_sections(client):
    memo = client.get("/api/memos/CM-2026-0101").json()
    assert [s["section_type"] for s in memo["sections"]] == [
        "business_overview", "industry_competition", "financial_performance",
        "liquidity_debt", "key_risks", "legal_regulatory",
    ]


def test_section_save_then_submit_locks_the_memo(client):
    r = client.put("/api/memos/CM-2026-0102/sections/key_risks",
                   json={"body": "Supplier concentration.", "updated_by": "m.lee@contoso.example"})
    assert r.status_code == 200
    assert client.post("/api/memos/CM-2026-0102/submit",
                       json={"actor": "m.lee@contoso.example"}).json()["status"] == "Submitted"
    locked = client.put("/api/memos/CM-2026-0102/sections/key_risks",
                        json={"body": "edit", "updated_by": "m.lee@contoso.example"})
    assert locked.status_code == 409


def test_restricted_list_is_flagged_but_not_enforced(client):
    # Legacy behaviour (pain point P5): the restriction is only a warning flag.
    tickers = {r["ticker"] for r in client.get("/api/restricted").json()}
    assert tickers == {"TSLA", "META"}
    assert client.get("/api/borrowers/B-1020").json()["restricted"] is True


def test_create_memo_creates_all_sections(client):
    memo_id = client.post("/api/memos", json={"borrower_id": "B-1003",
                                              "analyst_email": "m.lee@contoso.example"}).json()["memo_id"]
    assert len(client.get(f"/api/memos/{memo_id}").json()["sections"]) == 6
