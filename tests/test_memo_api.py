import pytest
from fastapi.testclient import TestClient

from policypilot.memo import api as memo_api
from policypilot.memo.store import DraftStore
from tests.test_memo_agent import DOC, FakeIndex, FakeLLM

ANALYST = "m.lee@contoso.example"


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

    def portfolio(self, analyst_email):
        return {"B-1"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    svc = memo_api.Services()
    portal = FakePortal()
    svc.__dict__.update(
        legacy=portal,
        store=DraftStore(tmp_path / "memo.db"),
        index=FakeIndex(),
        llm=FakeLLM("had $8.0 billion of commercial paper outstanding"),
    )
    monkeypatch.setattr(memo_api, "services", svc)
    monkeypatch.setattr(memo_api.Services, "model_label", property(lambda self: "fake-model"))
    with TestClient(memo_api.app) as c:
        c.fake_portal = portal
        yield c


URL = "/ai/drafts/CM-1/sections/liquidity_debt"


def test_full_human_in_the_loop_flow(client):
    v1 = client.post(f"{URL}/generate", json={"analyst_email": ANALYST}).json()
    assert v1["version_no"] == 1 and v1["origin"] == "ai" and v1["grounded"]

    v2 = client.post(
        f"{URL}/generate",
        json={
            "analyst_email": ANALYST,
            "feedback": "Mention the term notes.",
            "quotes": [
                {
                    "text": "fixed-rate notes",
                    "start": DOC.index("fixed-rate"),
                    "end": DOC.index("fixed-rate") + 16,
                }
            ],
        },
    ).json()
    assert (
        v2["version_no"] == 2
        and v2["based_on"] == 1
        and v2["feedback"] == "Mention the term notes."
    )

    # time travel back to v1, then approve it
    assert (
        client.post(f"{URL}/current", json={"analyst_email": ANALYST, "version_no": 1}).json()[
            "current_version"
        ]
        == 1
    )
    state = client.post(f"{URL}/approve", json={"analyst_email": ANALYST, "version_no": 1}).json()
    assert state["approved_version"] == 1

    v3 = client.post(
        f"{URL}/edit", json={"analyst_email": ANALYST, "text": v1["text"] + " Edited."}
    ).json()
    assert v3["origin"] == "human" and v3["citations"][0]["verified"]

    saved = client.post(f"{URL}/saved", json={"analyst_email": ANALYST, "version_no": 1}).json()
    assert saved["saved_version"] == 1

    draft = client.get("/ai/drafts/CM-1", params={"analyst": ANALYST}).json()
    section = next(s for s in draft["sections"] if s["section_type"] == "liquidity_debt")
    assert [v["version_no"] for v in section["versions"]] == [1, 2, 3]
    assert len(client.get("/ai/drafts/CM-1/events").json()) >= 5


def test_restricted_borrower_is_refused_and_logged(client):
    client.fake_portal.restricted = {"B-1"}
    r = client.post(f"{URL}/generate", json={"analyst_email": ANALYST})
    assert r.status_code == 403
    assert r.json()["detail"]["refusal_reason"] == "restricted_borrower"
    assert any("refused" in e["action"] for e in client.get("/ai/drafts/CM-1/events").json())


def test_submitted_memo_cannot_be_drafted(client):
    client.fake_portal.status = "Submitted"
    assert client.post(f"{URL}/generate", json={"analyst_email": ANALYST}).status_code == 409
