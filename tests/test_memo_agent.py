import json

from policypilot.memo.agent import find_quote, run_section
from policypilot.memo.index import Chunk, chunk_document

DOC = "\n".join(
    [
        "Item 1. Business",
        "The Company designs, manufactures and markets smartphones and personal computers.",
        "Liquidity and Capital Resources",
        "As of September 27, 2025, the Company had $8.0 billion of commercial paper outstanding.",
        "The Company’s fixed-rate notes total $91.3 billion with maturities through 2062.",
        "Legal Proceedings",
        "The Company is subject to various legal proceedings and claims.",
    ]
)


def test_chunk_document_keeps_exact_offsets():
    chunks = chunk_document(7, DOC, target_words=12)
    assert len(chunks) > 1
    for c in chunks:
        assert DOC[c.start : c.end] == c.text
        assert c.line_start <= c.line_end
    assert chunks[0].line_start == 1 and chunks[-1].line_end == 7


def test_find_quote_tolerates_whitespace_case_and_curly_quotes():
    hit = find_quote(DOC, 0, len(DOC), "The Company's FIXED-RATE notes   total $91.3 billion")
    assert hit is not None
    assert DOC[hit[0] : hit[1]].startswith("The Company’s fixed-rate notes")
    assert find_quote(DOC, 0, len(DOC), "The Company has no debt at all") is None


class FakeLegacy:
    def __init__(self, restricted=frozenset(), portfolio=frozenset({"B-1"})):
        self._restricted, self._portfolio = set(restricted), set(portfolio)

    def restricted_ids(self):
        return self._restricted

    def portfolio(self, analyst_email):
        return self._portfolio


class FakeIndex:
    def __init__(self):
        self.chunks = chunk_document(7, DOC, target_words=12)

    def ensure_indexed(self, filing_id, text):
        return 0

    def search(self, query, filing_id, k=4):
        words = set(query.lower().split())
        scored = sorted(self.chunks, key=lambda c: -len(words & set(c.text.lower().split())))
        return [Chunk(**{**c.to_dict(), "score": 0.5}) for c in scored[:k]]

    def overlapping(self, filing_id, start, end):
        return [
            Chunk(**{**c.to_dict(), "score": 1.0})
            for c in self.chunks
            if c.start < end and c.end > start
        ]


class FakeLLM:
    def __init__(self, quote):
        self.quote = quote
        self.prompts = []

    def complete(self, system, messages, max_tokens=1024):
        self.prompts.append(messages[-1]["content"])
        if system.startswith("You help a bank credit analyst"):
            return json.dumps({"queries": ["notes maturities"]})
        source = next(
            line.split("]")[0][1:]
            for line in messages[-1]["content"].splitlines()
            if line.startswith("[S") and "commercial paper" in messages[-1]["content"]
        )
        return json.dumps(
            {
                "draft": "The borrower had $8.0 billion of commercial paper outstanding [1].",
                "citations": [{"n": 1, "source": source, "quote": self.quote}],
                "reasoning": "Used the liquidity section.",
            }
        )


MEMO = {"memo_id": "CM-1"}
BORROWER = {"borrower_id": "B-1", "name": "Example Corp", "ticker": "EXM"}
FILING = {"filing_id": 7, "accession_number": "0000000000-25-000001", "filing_date": "2025-10-31"}


def _run(llm, legacy=None, **kw):
    return run_section(
        llm,
        FakeIndex(),
        legacy or FakeLegacy(),
        memo=MEMO,
        borrower=BORROWER,
        filing=FILING,
        document=DOC,
        section_type="liquidity_debt",
        analyst_email="m.lee@contoso.example",
        **kw,
    )


def test_verified_citation_is_mapped_to_exact_filing_position():
    out = _run(FakeLLM("had $8.0 billion of commercial paper outstanding"))
    assert out["grounded"] is True and out["refusal_reason"] is None
    c = out["citations"][0]
    assert c["verified"] is True
    assert DOC[c["start"] : c["end"]] == "had $8.0 billion of commercial paper outstanding"
    assert c["line_start"] == 4
    assert out["trace"]["guard"]["allowed"] is True
    assert out["trace"]["queries"]


def test_invented_quote_is_flagged_and_answer_not_grounded():
    out = _run(FakeLLM("the Company had $12 billion in a revolving credit facility"))
    assert out["grounded"] is False
    assert out["refusal_reason"] == "no_grounded_answer"
    assert out["citations"][0]["verified"] is False
    assert out["warnings"]


def test_guard_refuses_restricted_borrower_before_any_llm_call():
    llm = FakeLLM("anything")
    out = _run(llm, legacy=FakeLegacy(restricted={"B-1"}))
    assert out["refusal_reason"] == "restricted_borrower"
    assert llm.prompts == []


def test_guard_refuses_borrower_outside_analyst_portfolio():
    out = _run(FakeLLM("anything"), legacy=FakeLegacy(portfolio=set()))
    assert out["refusal_reason"] == "not_in_portfolio"


def test_feedback_quote_is_pinned_into_sources_and_prompt():
    start = DOC.index("The Company’s fixed-rate notes")
    quote = {"text": "fixed-rate notes total $91.3 billion", "start": start, "end": start + 60}
    llm = FakeLLM("had $8.0 billion of commercial paper outstanding")
    out = _run(
        llm, feedback="Also mention the term notes.", quotes=[quote], previous_draft="Old draft."
    )
    assert any(s["pinned"] for s in out["trace"]["sources"])
    draft_prompt = llm.prompts[-1]
    assert "Analyst feedback to address" in draft_prompt and "fixed-rate notes" in draft_prompt
    assert "notes maturities" in out["trace"]["queries"]


TABLE_DOC = "Net sales by region\nU.S.\n$\n151,790\n$\n140,000\nChina\n64,377\n70,000\n"
RISK_DOC = (
    "Defending against litigation or responding to government investigations can be "
    "expensive, time-consuming and disruptive to the Company's operations."
)


def test_quote_matches_table_cells_split_across_lines():
    hit = find_quote(TABLE_DOC, 0, len(TABLE_DOC), "U.S. $151,790")
    assert hit is not None and hit[2] == "exact"
    assert TABLE_DOC[hit[0] : hit[1]] == "U.S.\n$\n151,790"


def test_near_exact_copy_is_accepted_and_labelled():
    # non-breaking hyphen + one stray letter: a faithful copy, not a paraphrase
    quote = "responding to governments investigations can be expensive, time‑consuming"
    hit = find_quote(RISK_DOC, 0, len(RISK_DOC), quote)
    assert hit is not None and hit[2] == "near"
    assert find_quote(RISK_DOC, 0, len(RISK_DOC), quote, allow_near=False) is None


def test_stitched_quote_is_rejected():
    # cells taken from different columns of a table are not a verbatim quote
    assert find_quote(TABLE_DOC, 0, len(TABLE_DOC), "U.S. $151,790 China 70,000") is None


class MarkerlessThenFixedLLM(FakeLLM):
    """First answer forgets the [n] markers; the repair attempt adds them back."""

    def complete(self, system, messages, max_tokens=1024):
        if messages[-1]["content"].startswith("Your draft has no [n] citation markers"):
            out = json.loads(messages[-2]["content"])
            out["draft"] = out["draft"].rstrip(".") + " [1]."
            return json.dumps(out)
        out = json.loads(super().complete(system, messages, max_tokens))
        out["draft"] = out["draft"].replace(" [1]", "")
        return json.dumps(out)


def test_missing_citation_markers_are_repaired_once():
    out = _run(MarkerlessThenFixedLLM("had $8.0 billion of commercial paper outstanding"))
    assert out["grounded"] is True
    assert out["trace"]["llm_calls"] == 2
