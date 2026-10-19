from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from policypilot.memo import api as memo_api
from policypilot.memo.auth import TokenValidator
from policypilot.memo.store import DraftStore
from tests.test_memo_agent import DOC, FakeIndex, FakeLLM

ANALYST = "m.lee@contoso.example"
OTHER_ANALYST = "a.ruiz@contoso.example"
OFFICER = "p.raman@contoso.example"
ISSUER, AUDIENCE = "https://idp.test", "api://contoso-credit-portal"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(email: str, roles: list[str], key=KEY, **overrides) -> dict:
    now = datetime.now(UTC)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "preferred_username": email,
        "name": email,
        "roles": roles,
        "iat": now,
        "exp": now + timedelta(hours=1),
        **overrides,
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, key, algorithm='RS256')}"}


MARCUS = token(ANALYST, ["Credit.Analyst"])
ANA = token(OTHER_ANALYST, ["Credit.Analyst"])
PRIYA = token(OFFICER, ["Credit.Officer"])


class FakePortal:
    def __init__(self):
        self.status = "Draft"
        self.restricted = set()

    def memo(self, memo_id):
        return {
            "memo_id": memo_id,
            "borrower_id": "B-1",
            "borrower_name": "Example Corp",
            "ticker": "EXM",
            "analyst_email": ANALYST,
            "review_year": 2026,
            "status": self.status,
            "sections": [{"section_type": "liquidity_debt", "body": ""}],
        }

    def borrower(self, borrower_id):
        return {
            "borrower_id": "B-1",
            "name": "Example Corp",
            "ticker": "EXM",
            "sector": "Tech",
            "restricted": False,
            "filings": [
                {
                    "filing_id": 7,
                    "accession_number": "0000000000-25-000001",
                    "filing_date": "2025-10-31",
                }
            ],
        }

    def filing_text(self, filing_id):
        return DOC

    def restricted_ids(self):
        return self.restricted

    def portfolio(self):
        return {"B-1"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    svc = memo_api.Services()
    portal = FakePortal()
    svc.__dict__.update(
        validator=TokenValidator(issuer=ISSUER, audience=AUDIENCE, key=KEY.public_key()),
        store=DraftStore(tmp_path / "memo.db"),
        index=FakeIndex(),
        llm=FakeLLM("had $8.0 billion of commercial paper outstanding"),
    )
    svc.legacy_for = lambda user: portal
    monkeypatch.setattr(memo_api, "services", svc)
    monkeypatch.setattr(memo_api.Services, "model_label", property(lambda self: "fake-model"))
    with TestClient(memo_api.app) as c:
        c.fake_portal = portal
        yield c


URL = "/ai/drafts/CM-1/sections/liquidity_debt"


def test_full_human_in_the_loop_flow(client):
    v1 = client.post(f"{URL}/generate", json={}, headers=MARCUS).json()
    assert v1["version_no"] == 1 and v1["origin"] == "ai" and v1["grounded"]
    assert v1["created_by"] == ANALYST  # attributed from the token

    start = DOC.index("fixed-rate")
    v2 = client.post(
        f"{URL}/generate",
        headers=MARCUS,
        json={
            "feedback": "Mention the term notes.",
            "quotes": [{"text": "fixed-rate notes", "start": start, "end": start + 16}],
        },
    ).json()
    assert v2["version_no"] == 2 and v2["based_on"] == 1

    current = client.post(f"{URL}/current", json={"version_no": 1}, headers=MARCUS).json()
    assert current["current_version"] == 1  # time travel back to v1
    state = client.post(f"{URL}/approve", json={"version_no": 1}, headers=MARCUS).json()
    assert state["approved_version"] == 1

    v3 = client.post(f"{URL}/edit", json={"text": v1["text"] + " Edited."}, headers=MARCUS).json()
    assert v3["origin"] == "human" and v3["citations"][0]["verified"]

    saved = client.post(f"{URL}/saved", json={"version_no": 1}, headers=MARCUS).json()
    assert saved["saved_version"] == 1

    draft = client.get("/ai/drafts/CM-1", headers=MARCUS).json()
    section = next(s for s in draft["sections"] if s["section_type"] == "liquidity_debt")
    assert [v["version_no"] for v in section["versions"]] == [1, 2, 3]
    assert draft["access"]["can_draft"] is True
    assert len(client.get("/ai/drafts/CM-1/events", headers=MARCUS).json()) >= 5


def test_requests_without_a_valid_token_are_rejected(client):
    assert client.get("/ai/drafts/CM-1").status_code == 401
    forged = token(
        ANALYST,
        ["Credit.Analyst"],
        key=rsa.generate_private_key(public_exponent=65537, key_size=2048),
    )
    assert client.post(f"{URL}/generate", json={}, headers=forged).status_code == 401
    wrong_audience = token(ANALYST, ["Credit.Analyst"], aud="api://something-else")
    assert client.get("/ai/drafts/CM-1", headers=wrong_audience).status_code == 401


def test_another_analyst_cannot_view_or_draft(client):
    assert client.get("/ai/drafts/CM-1", headers=ANA).status_code == 403
    assert client.post(f"{URL}/generate", json={}, headers=ANA).status_code == 403


def test_credit_officer_gets_read_only_access(client):
    client.post(f"{URL}/generate", json={}, headers=MARCUS)
    draft = client.get("/ai/drafts/CM-1", headers=PRIYA)
    assert draft.status_code == 200 and draft.json()["access"]["can_draft"] is False
    assert client.get(f"{URL}/versions/1", headers=PRIYA).status_code == 200
    assert client.post(f"{URL}/generate", json={}, headers=PRIYA).status_code == 403
    assert client.post(f"{URL}/approve", json={"version_no": 1}, headers=PRIYA).status_code == 403


def test_restricted_borrower_is_refused_and_logged(client):
    client.fake_portal.restricted = {"B-1"}
    r = client.post(f"{URL}/generate", json={}, headers=MARCUS)
    assert r.status_code == 403
    assert r.json()["detail"]["refusal_reason"] == "restricted_borrower"
    events = client.get("/ai/drafts/CM-1/events", headers=MARCUS).json()
    assert any("refused" in e["action"] for e in events)


def test_submitted_memo_cannot_be_drafted(client):
    client.fake_portal.status = "Submitted"
    assert client.post(f"{URL}/generate", json={}, headers=MARCUS).status_code == 409
