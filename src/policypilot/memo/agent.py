"""One agent run drafts ONE credit memo section: guard -> plan -> retrieve -> draft -> verify.

The verify step is stricter than the POC's: every citation must carry a short verbatim quote,
and that quote must actually be found in the cited source passage. Verified quotes are mapped
to exact character and line positions in the filing, which the UI uses to highlight them.
"""

from __future__ import annotations

import json
import re
import time
from difflib import SequenceMatcher
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from policypilot.memo.index import Chunk, FilingIndex
from policypilot.memo.legacy_client import LegacyPortal
from policypilot.memo.sections import SECTION_BY_KEY

MAX_SOURCES = 10
CITATION_RE = re.compile(r"\[(\d+)\]")

PLAN_PROMPT = (
    "You help a bank credit analyst search a company's 10-K filing. Turn the analyst's feedback "
    "on a credit memo section into at most 2 short, specific search queries for a semantic "
    'index over the filing text. Reply with ONLY JSON: {"queries": ["...", "..."]}'
)

DRAFT_PROMPT = """You draft ONE section of a commercial credit memo for Contoso Bank's Commercial \
Credit Risk team, using ONLY the numbered sources from the borrower's latest 10-K.

Rules:
- Professional credit-memo prose, 120-220 words, no headings, no bullet lists.
- Every sentence that states a fact ends with a citation marker like [1] or [2].
- Each citation number maps to exactly one source (S1, S2, ...) and carries a short quote \
(at most 40 words) copied VERBATIM, character for character, from that source.
- Quote figures exactly as the source states them. Never use outside knowledge or speculate.
- If the analyst gave feedback, address it directly; analyst-quoted excerpts must be used.
- If the sources do not support this section, return an empty draft and say why.
- "reasoning": 2-4 sentences explaining which sources you relied on and why, and how you \
handled the analyst's feedback (if any).

Reply with ONLY this JSON object:
{"draft": "...", "citations": [{"n": 1, "source": "S1", "quote": "..."}], "reasoning": "..."}"""


class SectionState(TypedDict, total=False):
    memo_id: str
    borrower_id: str
    borrower_name: str
    ticker: str
    analyst_email: str
    section_type: str
    filing: dict
    feedback: str
    quotes: list[dict]
    previous_draft: str
    guard: dict
    queries: list[str]
    sources: list[dict]
    draft: str
    citations: list[dict]
    reasoning: str
    raw_output: str
    grounded: bool
    refusal_reason: str | None
    warnings: list[str]
    llm_calls: int


# ------------------------------------------------------------------ quote verification

# Same-length character normalisation, so offsets in the normalised text match the original.
_NORMALISE = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',  # curly quotes
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)
NEAR_MIN_MATCHED = 0.92  # share of the quote's characters found, in order, in the filing...
NEAR_MAX_SPAN = 1.10  # ...within a window at most this much longer than the quote itself


def _compact(text: str) -> tuple[str, list[int]]:
    """Lower-case text with every whitespace character removed, plus a map back to the
    original offsets. 10-K tables put cells on separate lines ("$" / "151,790"), so the
    model's "$151,790" only matches once whitespace is ignored entirely."""
    chars, index = [], []
    for i, ch in enumerate(text.translate(_NORMALISE)):
        if not ch.isspace():
            chars.append(ch.lower())
            index.append(i)
    return "".join(chars), index


def _match(segment: str, quote: str, allow_near: bool) -> tuple[int, int, str] | None:
    seg, index = _compact(segment)
    parts = [p for p in re.split(r"\.\.\.|\u2026", quote) if len(p.split()) >= 3] or [quote]
    q, _ = _compact(max(parts, key=len))  # with an ellipsis, verify the longest fragment
    if len(q) < 12:
        return None
    pos = seg.find(q)
    if pos >= 0:
        return index[pos], index[pos + len(q) - 1] + 1, "exact"
    if not allow_near:
        return None
    blocks = [
        b
        for b in SequenceMatcher(None, q, seg, autojunk=False).get_matching_blocks()
        if b.size >= 3
    ]
    if not blocks:
        return None
    matched = sum(b.size for b in blocks)
    first, last = blocks[0].b, blocks[-1].b + blocks[-1].size
    if matched >= NEAR_MIN_MATCHED * len(q) and (last - first) <= NEAR_MAX_SPAN * len(q):
        return index[first], index[last - 1] + 1, "near"
    return None


def find_quote(
    document: str, start: int, end: int, quote: str, allow_near: bool = True
) -> tuple[int, int, str] | None:
    """Locate `quote` in document[start:end]. Returns absolute (start, end, kind) where kind is
    "exact" (identical apart from whitespace, case, curly quotes and dash variants) or "near"
    (tiny copy differences, e.g. a dropped letter), or None if the quote isn't in the passage.
    Stitched-together or paraphrased quotes fail the span check and are rejected."""
    quote = quote.strip().strip('"').strip()
    hit = _match(document[start:end], quote, allow_near)
    return (start + hit[0], start + hit[1], hit[2]) if hit else None


def _line_of(document: str, offset: int) -> int:
    return document.count("\n", 0, offset) + 1


def _parse_json(raw: str) -> dict:
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no JSON object in model output")
    return json.loads(s[i : j + 1])


# ------------------------------------------------------------------ graph


def build_section_graph(llm: Any, index: FilingIndex, legacy: LegacyPortal, document: str):
    """`document` is the full filing text the run cites from (already fetched by the caller)."""

    def guard_node(state: SectionState) -> SectionState:
        bid = state["borrower_id"]
        if bid in legacy.restricted_ids():
            return {
                "guard": {
                    "allowed": False,
                    "reason": "restricted_borrower",
                    "detail": "Borrower is on the Compliance Restricted List.",
                },
                "grounded": False,
                "refusal_reason": "restricted_borrower",
            }
        if bid not in legacy.portfolio(state["analyst_email"]):
            return {
                "guard": {
                    "allowed": False,
                    "reason": "not_in_portfolio",
                    "detail": "Borrower is not in this analyst's portfolio.",
                },
                "grounded": False,
                "refusal_reason": "not_in_portfolio",
            }
        return {
            "guard": {
                "allowed": True,
                "reason": None,
                "detail": "Not restricted; borrower is in the analyst's portfolio.",
            }
        }

    def plan_node(state: SectionState) -> SectionState:
        spec = SECTION_BY_KEY[state["section_type"]]
        queries = list(spec.queries)
        calls = state.get("llm_calls", 0)
        feedback = (state.get("feedback") or "").strip()
        if feedback:
            try:
                reply = llm.complete(
                    PLAN_PROMPT,
                    [
                        {
                            "role": "user",
                            "content": f"Section: {spec.title}\nAnalyst feedback: {feedback}",
                        }
                    ],
                    max_tokens=400,
                )
                calls += 1
                extra = [q for q in _parse_json(reply).get("queries", []) if isinstance(q, str)]
            except Exception:  # planning is best-effort; fall back to the raw feedback
                extra = []
            queries += extra[:2] or [feedback[:200]]
        return {"queries": queries, "llm_calls": calls}

    def retrieve_node(state: SectionState) -> SectionState:
        filing_id = state["filing"]["filing_id"]
        found: dict[str, Chunk] = {}
        pinned: set[str] = set()
        for q in state.get("quotes") or []:
            for c in index.overlapping(filing_id, int(q["start"]), int(q["end"])):
                found[c.chunk_id] = c
                pinned.add(c.chunk_id)
        for query in state["queries"]:
            for c in index.search(query, filing_id, k=4):
                if c.chunk_id in pinned:
                    continue
                if c.chunk_id not in found or found[c.chunk_id].score < c.score:
                    found[c.chunk_id] = c
        ranked = sorted(found.values(), key=lambda c: (c.chunk_id not in pinned, -c.score))
        ranked = ranked[:MAX_SOURCES]
        ranked.sort(key=lambda c: c.start)  # present sources in document order
        sources = [
            {"id": f"S{i}", **c.to_dict(), "pinned": c.chunk_id in pinned}
            for i, c in enumerate(ranked, start=1)
        ]
        return {"sources": sources}

    def draft_node(state: SectionState) -> SectionState:
        spec = SECTION_BY_KEY[state["section_type"]]
        if not state.get("sources"):
            return {
                "draft": "",
                "citations": [],
                "reasoning": "No passages were retrieved.",
                "raw_output": "",
            }
        src_block = "\n\n".join(
            f"[{s['id']}] (lines {s['line_start']}-{s['line_end']}"
            f"{', quoted by analyst' if s['pinned'] else ''})\n{s['text']}"
            for s in state["sources"]
        )
        parts = [
            f"Borrower: {state['borrower_name']} ({state['ticker']}), 10-K filed "
            f"{state['filing']['filing_date']}.",
            f"Section: {spec.title}\nWhat to cover: {spec.goal}",
        ]
        if state.get("previous_draft"):
            parts.append(f"Previous draft of this section:\n{state['previous_draft']}")
        if (state.get("feedback") or "").strip():
            parts.append(f"Analyst feedback to address:\n{state['feedback'].strip()}")
        if state.get("quotes"):
            parts.append(
                "Excerpts the analyst quoted from the filing:\n"
                + "\n".join(f'- "{q["text"]}"' for q in state["quotes"])
            )
        parts.append(f"Sources:\n{src_block}")
        messages = [{"role": "user", "content": "\n\n".join(parts)}]
        calls = state.get("llm_calls", 0)
        raw = llm.complete(DRAFT_PROMPT, messages, max_tokens=4000)
        calls += 1
        try:
            parsed = _parse_json(raw)
        except Exception:
            messages += [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": "That was not valid JSON. Reply with ONLY the JSON object.",
                },
            ]
            raw = llm.complete(DRAFT_PROMPT, messages, max_tokens=4000)
            calls += 1
            try:
                parsed = _parse_json(raw)
            except Exception:
                parsed = {
                    "draft": "",
                    "citations": [],
                    "reasoning": "The model did not return a valid structured answer.",
                }
        if parsed.get("citations") and not CITATION_RE.search(str(parsed.get("draft") or "")):
            # Quotes came back but the prose has no [n] markers, so nothing ties a sentence to
            # its evidence. One repair attempt; if it still has none, verify() flags it.
            messages += [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": "Your draft has no [n] citation markers. Return the same "
                    "JSON, with every factual sentence in the draft ending in the matching [n].",
                },
            ]
            retry = llm.complete(DRAFT_PROMPT, messages, max_tokens=4000)
            calls += 1
            try:
                repaired = _parse_json(retry)
                if CITATION_RE.search(str(repaired.get("draft") or "")):
                    parsed, raw = repaired, retry
            except Exception:
                pass
        return {
            "draft": str(parsed.get("draft") or "").strip(),
            "citations": parsed.get("citations") or [],
            "reasoning": str(parsed.get("reasoning") or "").strip(),
            "raw_output": raw[:4000],
            "llm_calls": calls,
        }

    def verify_node(state: SectionState) -> SectionState:
        by_id = {s["id"]: s for s in state.get("sources", [])}
        verified: list[dict] = []
        warnings: list[str] = []
        for c in state.get("citations", []):
            try:
                n = int(c.get("n"))
            except (TypeError, ValueError):
                continue
            src = by_id.get(str(c.get("source", "")).strip())
            quote = str(c.get("quote") or "")
            # Prefer an exact match in the cited passage, then anywhere in the run's sources (the
            # model sometimes cites the neighbouring passage), and only then a near-exact match.
            candidates = ([src] if src else []) + [o for o in by_id.values() if o is not src]
            hit = None
            for allow_near in (False, True):
                for cand in candidates:
                    hit = find_quote(document, cand["start"], cand["end"], quote, allow_near)
                    if hit:
                        src = cand
                        break
                if hit:
                    break
            entry = {
                "n": n,
                "source": src["id"] if src else c.get("source"),
                "quote": quote,
                "verified": bool(hit),
                "filing_id": state["filing"]["filing_id"],
            }
            if hit:
                entry.update(
                    match=hit[2],
                    start=hit[0],
                    end=hit[1],
                    line_start=_line_of(document, hit[0]),
                    line_end=_line_of(document, hit[1]),
                )
            else:
                warnings.append(f"Citation [{n}]: quote not found in the filing.")
            verified.append(entry)

        draft = state.get("draft", "")
        used = {int(m) for m in CITATION_RE.findall(draft)}
        ok = {c["n"] for c in verified if c["verified"]}
        missing = sorted(used - {c["n"] for c in verified})
        if missing:
            warnings.append(f"Citation markers without a source: {missing}.")
        if draft and not used:
            warnings.append("Draft contains no citation markers.")
        grounded = bool(draft) and bool(used) and used <= ok
        refusal = None
        if not draft or not ok:
            refusal = "no_grounded_answer"
            grounded = False
        return {
            "citations": sorted(verified, key=lambda c: c["n"]),
            "grounded": grounded,
            "refusal_reason": refusal,
            "warnings": warnings,
        }

    g = StateGraph(SectionState)
    for name, fn in [
        ("guard", guard_node),
        ("plan", plan_node),
        ("retrieve", retrieve_node),
        ("draft", draft_node),
        ("verify", verify_node),
    ]:
        g.add_node(name, fn)
    g.set_entry_point("guard")
    g.add_conditional_edges("guard", lambda s: "plan" if s["guard"]["allowed"] else END)
    g.add_edge("plan", "retrieve")
    g.add_edge("retrieve", "draft")
    g.add_edge("draft", "verify")
    g.add_edge("verify", END)
    return g.compile()


def run_section(
    llm: Any,
    index: FilingIndex,
    legacy: LegacyPortal,
    *,
    memo: dict,
    borrower: dict,
    filing: dict,
    document: str,
    section_type: str,
    analyst_email: str,
    feedback: str = "",
    quotes: list[dict] | None = None,
    previous_draft: str = "",
    model_label: str = "",
) -> dict:
    """Run the graph for one section and return a version payload (text, citations, trace)."""
    t0 = time.perf_counter()
    graph = build_section_graph(llm, index, legacy, document)
    out: SectionState = graph.invoke(
        {
            "memo_id": memo["memo_id"],
            "borrower_id": borrower["borrower_id"],
            "borrower_name": borrower["name"],
            "ticker": borrower["ticker"],
            "analyst_email": analyst_email,
            "section_type": section_type,
            "filing": filing,
            "feedback": feedback,
            "quotes": quotes or [],
            "previous_draft": previous_draft,
            "llm_calls": 0,
        }
    )
    sources = [
        {
            k: s[k]
            for k in ("id", "chunk_id", "score", "start", "end", "line_start", "line_end", "pinned")
        }
        | {"preview": s["text"][:400]}
        for s in out.get("sources", [])
    ]
    return {
        "text": out.get("draft", ""),  # kept even when ungrounded, so the analyst can see why
        "citations": out.get("citations", []),
        "reasoning": out.get("reasoning", out.get("guard", {}).get("detail", "")),
        "grounded": bool(out.get("grounded")),
        "refusal_reason": out.get("refusal_reason"),
        "warnings": out.get("warnings", []),
        "trace": {
            "guard": out.get("guard"),
            "queries": out.get("queries", []),
            "sources": sources,
            "filing": {k: filing[k] for k in ("filing_id", "accession_number", "filing_date")},
            "model": model_label,
            "llm_calls": out.get("llm_calls", 0),
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "raw_output": out.get("raw_output", ""),
        },
    }
