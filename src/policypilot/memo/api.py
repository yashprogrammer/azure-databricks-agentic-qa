"""AI Credit Memo Draft service: the API behind the Credit Portal's new "AI Credit Memo Draft"
tab. Run locally with:

    uv run uvicorn policypilot.memo.api:app --port 8200

It reads the legacy Credit Portal (via its API), drafts sections with the PolicyPilot agent,
and keeps every version with full traces. It never writes to the legacy database: the portal
saves approved text into the memo itself.
"""

from __future__ import annotations

from functools import cached_property

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from policypilot.memo.agent import CITATION_RE, run_section
from policypilot.memo.legacy_client import LegacyApiClient
from policypilot.memo.sections import SECTION_BY_KEY, SECTIONS
from policypilot.memo.store import DraftStore


class Services:
    """Lazily-built dependencies (tests replace them with fakes)."""

    @cached_property
    def legacy(self):
        return LegacyApiClient()

    @cached_property
    def store(self):
        return DraftStore()

    @cached_property
    def index(self):
        from policypilot.memo.index import ChromaFilingIndex

        return ChromaFilingIndex()

    @cached_property
    def llm(self):
        from policypilot.agent.llm import get_llm_client

        return get_llm_client()

    @property
    def model_label(self) -> str:
        from policypilot.config import AI_GATEWAY_MODEL_SERVICE, GROQ_MODEL, get_settings

        return GROQ_MODEL if get_settings().is_local else AI_GATEWAY_MODEL_SERVICE


app = FastAPI(title="Contoso AI Credit Memo Draft service", version="1.0.0")
services = Services()


class GenerateRequest(BaseModel):
    analyst_email: str
    feedback: str = ""
    quotes: list[dict] = []  # [{"text", "start", "end", "line_start", "line_end"}] from the filing
    base_version: int | None = None


class EditRequest(BaseModel):
    analyst_email: str
    text: str
    base_version: int | None = None


class VersionAction(BaseModel):
    analyst_email: str
    version_no: int


# ------------------------------------------------------------------ helpers


def _section(section_type: str):
    if section_type not in SECTION_BY_KEY:
        raise HTTPException(404, f"Unknown section {section_type}")
    return SECTION_BY_KEY[section_type]


def _context(memo_id: str) -> tuple[dict, dict, dict | None]:
    try:
        memo = services.legacy.memo(memo_id)
    except Exception as e:  # legacy returns 404 for unknown memos
        raise HTTPException(404, f"Memo {memo_id} not found in the Credit Portal") from e
    borrower = services.legacy.borrower(memo["borrower_id"])
    filing = borrower["filings"][0] if borrower.get("filings") else None
    return memo, borrower, filing


def _require_editable(memo: dict) -> None:
    if memo["status"] not in ("Draft", "Returned"):
        raise HTTPException(
            409,
            f"Memo is {memo['status']}: AI drafting is only available for Draft or Returned memos",
        )


# ------------------------------------------------------------------ endpoints


@app.get("/ai/health")
def health():
    from policypilot.config import get_settings

    s = get_settings()
    return {
        "env": s.env,
        "model": services.model_label,
        "llm_configured": bool(s.groq_api_key) or not s.is_local,
    }


@app.get("/ai/drafts/{memo_id}")
def get_draft(memo_id: str, analyst: str):
    memo, borrower, filing = _context(memo_id)
    store = services.store
    store.ensure_draft(
        memo_id,
        borrower["borrower_id"],
        borrower["ticker"],
        memo["analyst_email"],
        filing["filing_id"] if filing else None,
    )
    legacy_sections = {s["section_type"]: s for s in memo["sections"]}
    sections = []
    for spec in SECTIONS:
        state = store.state(memo_id, spec.key)
        current = (
            store.version(memo_id, spec.key, state["current_version"])
            if state["current_version"]
            else None
        )
        sections.append(
            {
                "section_type": spec.key,
                "title": spec.title,
                "goal": spec.goal,
                "state": state,
                "versions": store.versions(memo_id, spec.key),
                "current": current,
                "legacy_body": legacy_sections.get(spec.key, {}).get("body", ""),
            }
        )
    return {
        "memo": {
            k: memo[k]
            for k in (
                "memo_id",
                "borrower_id",
                "borrower_name",
                "ticker",
                "analyst_email",
                "review_year",
                "status",
            )
        },
        "borrower": {
            k: borrower[k] for k in ("borrower_id", "name", "ticker", "sector", "restricted")
        },
        "filing": filing,
        "access": {
            "restricted": borrower["borrower_id"] in services.legacy.restricted_ids(),
            "in_portfolio": borrower["borrower_id"] in services.legacy.portfolio(analyst),
            "is_preparer": analyst == memo["analyst_email"],
        },
        "sections": sections,
    }


@app.get("/ai/drafts/{memo_id}/sections/{section_type}/versions/{version_no}")
def get_version(memo_id: str, section_type: str, version_no: int):
    _section(section_type)
    v = services.store.version(memo_id, section_type, version_no)
    if not v:
        raise HTTPException(404, "Version not found")
    return v


@app.post("/ai/drafts/{memo_id}/sections/{section_type}/generate")
def generate(memo_id: str, section_type: str, req: GenerateRequest):
    _section(section_type)
    memo, borrower, filing = _context(memo_id)
    _require_editable(memo)
    if not filing:
        raise HTTPException(409, "No 10-K on file for this borrower yet (nightly download pending)")
    store = services.store
    store.ensure_draft(
        memo_id,
        borrower["borrower_id"],
        borrower["ticker"],
        memo["analyst_email"],
        filing["filing_id"],
    )
    base_no = req.base_version or store.state(memo_id, section_type)["current_version"]
    base = store.version(memo_id, section_type, base_no) if base_no else None

    document = services.legacy.filing_text(filing["filing_id"])
    services.index.ensure_indexed(filing["filing_id"], document)
    result = run_section(
        services.llm,
        services.index,
        services.legacy,
        memo=memo,
        borrower=borrower,
        filing=filing,
        document=document,
        section_type=section_type,
        analyst_email=req.analyst_email,
        feedback=req.feedback,
        quotes=req.quotes,
        previous_draft=base["text"] if base and req.feedback else "",
        model_label=services.model_label,
    )
    if result["refusal_reason"] in ("restricted_borrower", "not_in_portfolio"):
        store.log(
            memo_id,
            section_type,
            req.analyst_email,
            f"AI run refused: {result['refusal_reason']}",
            req.feedback,
        )
        raise HTTPException(
            403,
            {
                "refusal_reason": result["refusal_reason"],
                "detail": result["trace"]["guard"]["detail"],
            },
        )
    return store.add_version(
        memo_id,
        section_type,
        origin="ai",
        text=result["text"],
        created_by=req.analyst_email,
        citations=result["citations"],
        reasoning=result["reasoning"],
        trace=result["trace"],
        feedback=req.feedback,
        quotes=req.quotes,
        based_on=base_no if req.feedback else None,
        grounded=result["grounded"],
        refusal_reason=result["refusal_reason"],
        warnings=result["warnings"],
    )


@app.post("/ai/drafts/{memo_id}/sections/{section_type}/edit")
def edit(memo_id: str, section_type: str, req: EditRequest):
    """Analyst edits the text by hand: stored as a new human version. Citations whose markers
    survive the edit are kept; the analyst owns everything else."""
    _section(section_type)
    memo, _, _ = _context(memo_id)
    _require_editable(memo)
    store = services.store
    base_no = req.base_version or store.state(memo_id, section_type)["current_version"]
    base = store.version(memo_id, section_type, base_no) if base_no else None
    used = {int(n) for n in CITATION_RE.findall(req.text)}
    kept = [c for c in (base["citations"] if base else []) if c["n"] in used]
    verified = {c["n"] for c in kept if c.get("verified")}
    return store.add_version(
        memo_id,
        section_type,
        origin="human",
        text=req.text.strip(),
        created_by=req.analyst_email,
        citations=kept,
        reasoning="Edited by analyst.",
        trace={"note": "Manual edit by analyst; no AI run.", "edited_from": base_no},
        based_on=base_no,
        grounded=bool(used) and used <= verified,
        warnings=[]
        if used <= verified
        else [f"Markers without a verified source: {sorted(used - verified)}"],
    )


@app.post("/ai/drafts/{memo_id}/sections/{section_type}/current")
def set_current(memo_id: str, section_type: str, req: VersionAction):
    """Time travel: make an older (or newer) version the working version again."""
    _section(section_type)
    try:
        services.store.set_current(memo_id, section_type, req.version_no, req.analyst_email)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return services.store.state(memo_id, section_type)


@app.post("/ai/drafts/{memo_id}/sections/{section_type}/approve")
def approve(memo_id: str, section_type: str, req: VersionAction):
    _section(section_type)
    v = services.store.version(memo_id, section_type, req.version_no)
    if not v:
        raise HTTPException(404, "Version not found")
    if not v["text"]:
        raise HTTPException(409, "An empty draft cannot be approved")
    services.store.approve(memo_id, section_type, req.version_no, req.analyst_email)
    return services.store.state(memo_id, section_type)


@app.post("/ai/drafts/{memo_id}/sections/{section_type}/saved")
def mark_saved(memo_id: str, section_type: str, req: VersionAction):
    """Called by the portal after it has written the approved text into the legacy memo."""
    _section(section_type)
    try:
        services.store.mark_saved(memo_id, section_type, req.version_no, req.analyst_email)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return services.store.state(memo_id, section_type)


@app.get("/ai/drafts/{memo_id}/events")
def events(memo_id: str):
    return services.store.events(memo_id)
