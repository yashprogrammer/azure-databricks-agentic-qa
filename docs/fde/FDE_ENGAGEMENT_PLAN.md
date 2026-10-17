# Contoso Bank × PolicyPilot — FDE Engagement Plan

> **Fictional scenario.** Contoso Bank is Microsoft's standard fictional company. Every
> person, number and quote in this document is invented for teaching. The figures marked
> *(discovery estimate)* are the kind of numbers an FDE would collect in interviews, not
> real data.

This plan frames PolicyPilot as a **forward deployed engineering (FDE) engagement**. An FDE
project has three pieces, and this repo now covers all three:

| Piece | What it is | Where it lives |
| --- | --- | --- |
| **Legacy system** | Contoso Bank's existing Credit Portal on Azure | To be built (see §13) |
| **POC** | PolicyPilot: a governed, cited Q&A agent over 10-K filings | This repo, already built and deployed |
| **Integrated system** | The POC plugged into the Credit Portal, with governance | To be built (see §7–§8) |

Why a bank's credit team: financial services is the largest customer vertical for FDE
roles (Databricks, OpenAI and Anthropic all hire FDEs specifically for financial
services), and banks bring the strictest AI governance (model risk management, audit,
information barriers). That gives learners the strongest interview story.

---

## 1. Client profile

**Contoso Bank** is a mid-size US commercial bank.

- **Business unit:** Commercial & Corporate Banking. It lends to about **300 corporate
  borrowers**, most of them public companies that file 10-Ks with the SEC.
- **Team in scope:** Commercial Credit Risk, about **60 credit analysts**.
- **Core workflow:** every borrower gets an **annual credit review**. The analyst reads
  the borrower's latest 10-K and writes a **credit memo**: business overview, risk
  factors, debt and liquidity, covenants, and a recommendation. A credit officer approves
  the memo.
- **Platform:** Azure-first. The bank already runs an Azure Databricks workspace for its
  data team, but the credit team doesn't use it yet.

## 2. Stakeholders

| Person (fictional) | Role | What they care about |
| --- | --- | --- |
| **Priya Raman** | Chief Credit Officer, **executive sponsor** | Review backlog, analyst capacity, regulator confidence |
| **Marcus Lee** | Lead Credit Analyst, **business owner** | Faster memos without losing accuracy; must trust every sentence |
| **Elena Novak** | Credit Portal engineering lead, **legacy system owner** | Don't break the portal; no new write paths into the database without review |
| **Sam Okafor** | Data platform lead (Azure Databricks) | Reuse the existing workspace; cost; ownership after handover |
| **Jordan Blake** | Model Risk Management (MRM) lead | Any AI is a "model": must be validated, explainable, monitored |
| **Aisha Karim** | Compliance officer | Information barriers: analysts must not research restricted borrowers |
| **Tom Fischer** | InfoSec | No data to public AI tools; keys in Key Vault; SSO only |
| **You** | Forward Deployed Engineer | Ship a production integration and hand it over |

## 3. Legacy system: current state

### 3.1 Architecture

```
                       ┌──────────────────────────────────────────────┐
  Analyst (browser) ──►│ Credit Portal  (Azure App Service, Python)   │
     Entra ID SSO      │  • Borrower list + 10-K viewer               │
                       │  • Keyword search (SQL full-text)            │
                       │  • Credit memo editor                        │
                       └───────────────┬──────────────────────────────┘
                                       │ reads/writes
                       ┌───────────────▼──────────────────────────────┐
                       │ Azure SQL Database  (system of record)       │
                       │  borrowers · analyst_portfolio · filings     │
                       │  credit_memos · memo_sections · restricted_list │
                       └───────────────▲──────────────────────────────┘
                                       │ metadata
  SEC EDGAR ──► Azure Function (nightly timer) ──► Azure Blob Storage (10-K HTML/PDF)
```

| Component | Azure service | Notes |
| --- | --- | --- |
| Credit Portal | App Service (Python web app) | Entra ID login; owned by Elena's team |
| Database | Azure SQL Database (serverless) | System of record for borrowers and memos |
| Filing downloader | Azure Function, timer trigger | Nightly; downloads the latest 10-K for every active borrower |
| Filing store | Blob Storage | Raw 10-K documents; the portal's viewer links to them |
| Secrets | Key Vault | DB connection string, SEC contact email |

### 3.2 Data model (simplified)

| Table | Key columns |
| --- | --- |
| `borrowers` | `borrower_id`, `ticker`, `cik`, `name`, `sector`, `status` |
| `analyst_portfolio` | `analyst_email`, `borrower_id` |
| `filings` | `filing_id`, `borrower_id`, `accession_number`, `filing_date`, `blob_url` |
| `credit_memos` | `memo_id`, `borrower_id`, `analyst_email`, `status`, `review_year` |
| `memo_sections` | `section_id`, `memo_id`, `section_type`, `body`, `updated_by` |
| `restricted_list` | `borrower_id`, `reason`, `effective_from`, `effective_to` |

### 3.3 Today's workflow

1. The analyst opens the borrower in the Credit Portal and opens the 10-K (100–300 pages).
2. They search keywords ("liquidity", "covenant") and read the surrounding pages.
3. They copy paragraphs into the memo editor and rewrite them as memo sections.
4. A credit officer reviews the memo, then approves or sends it back.

## 4. Problem statement

### 4.1 In the sponsor's words

> "My analysts spend most of review season reading, not analyzing. Half of them are quietly
> pasting filings into ChatGPT, which InfoSec has banned, and MRM won't approve any AI
> tool we can't explain or audit." — Priya Raman, Chief Credit Officer

### 4.2 Pain points

| # | Pain | Evidence *(discovery estimate)* | Root cause |
| --- | --- | --- | --- |
| P1 | Memo drafting is slow | 2–3 days per borrower; ~40% of reviews late in Q1 | Manual reading of long filings |
| P2 | Search misses meaning | Analysts report missing relevant disclosures | Keyword search only ("supply chain" ≠ "single-source suppliers") |
| P3 | **Shadow AI** | Analysts admit using public chatbots | No approved tool; data leaves the bank; answers have no sources |
| P4 | **MRM blocks AI adoption** | Two earlier pilots rejected | No validation evidence, no explainability, no monitoring |
| P5 | **Information barriers** enforced by policy only | Manual attestations each quarter | Nothing in the system stops research on restricted borrowers |
| P6 | No audit trail | Compliance can't answer "who asked what" | Portal logs page views only |

### 4.3 Success metrics (agreed at proposal stage)

| Metric | Target |
| --- | --- |
| Time to first draft of a memo's risk and liquidity sections | −50% versus baseline |
| Grounded answers on the golden question set | ≥ 90% judged grounded by the evaluation harness |
| Answers with no citation shown to analysts | 0 (the citation gate refuses instead) |
| Questions about restricted borrowers answered | 0 |
| AI requests captured in the audit log | 100% |
| Off-topic questions refused | ≥ 95% |

### 4.4 Out of scope

- Making or approving credit decisions. The AI drafts; humans decide.
- Credit rating models and default probability models.
- Non-SEC documents (private borrowers' financial statements) in phase one.

## 5. Solution options (presented at the proposal meeting)

| Option | Pros | Cons | Decision |
| --- | --- | --- | --- |
| A. Approve a public chatbot | Fast | Data leaves the bank; no citations; fails MRM and InfoSec | ❌ |
| B. Buy a vendor research copilot | Polished UI | Not integrated with the Credit Portal; data in a vendor cloud; long procurement | ❌ |
| C. Fine-tune an LLM on filings | Domain tone | Expensive; still hallucinates; can't cite; filings change every year | ❌ |
| **D. Governed RAG agent on the bank's Azure Databricks** | Data stays in the bank's Azure; cited answers; reuses Unity Catalog governance; integrates through an API | Needs an integration build | ✅ |

## 6. The POC: PolicyPilot

### 6.1 What the POC proves

The POC is the project in this repo, scoped to 20 public companies standing in for
Contoso's borrowers. It shows that option D works before the bank commits to integration.

| Pain | POC capability | Evidence for the POC review |
| --- | --- | --- |
| P1, P2 | Semantic retrieval scoped to one company; LangGraph plan → retrieve → answer → verify | Live demo on real 10-Ks |
| P3 | LLM reached only through a **Unity AI Gateway** model service; the key lives in Key Vault | Architecture review with InfoSec |
| P4 | Every sentence cited `[n]`, with a Sources panel; uncited answers are replaced by a refusal; **evaluation harness** (safety, relevance, groundedness) | Evaluation report for MRM |
| P6 | Gateway usage tracking | Usage table shown to Compliance |
| Data governance | **Unity Catalog** tables, index and model service, with grants | Permissions walkthrough |

### 6.2 POC exit criteria (sign-off)

- Groundedness ≥ 90% and off-topic refusal ≥ 95% on the golden set.
- InfoSec accepts the key-handling and data-flow design.
- MRM accepts the evaluation approach as the basis for formal validation.
- Sponsor approves moving to integration.

### 6.3 POC gaps (why it isn't production yet)

| Gap in the POC | Needed for production |
| --- | --- |
| 20 hardcoded tickers | Borrower list driven by the bank's database |
| Manual seed notebook | Scheduled, monitored ingestion |
| Standalone Streamlit app | Answers inside the Credit Portal where analysts work |
| No information-barrier check | Restricted borrowers blocked in the system |
| Answers live only in the chat | Cited drafts saved into the credit memo |
| Usage tracking only | Full audit trail and monitoring for MRM and Compliance |

## 7. Integrated system: target state

### 7.1 Architecture

```
  Analyst ──► Credit Portal (App Service)  ── legacy UI + one new tab: "AI Credit Memo Draft"
                 │  1. POST /ai/drafts/{memo}/sections/{section}/generate  (one run per section)
                 ▼
          AI Credit Memo Draft service (PolicyPilot agent, Azure Databricks)
           guard → plan → retrieve → draft → verify  ──► versioned drafts + traces
             │            │                 │
             │            ▼                 ▼
             │   Vector Search index   Unity AI Gateway model service ──► Groq LLM
             │   (Delta Sync)          (usage + inference tables)
             │            ▲
             │   UC Delta table: chunks ◄── Lakeflow ingestion job ◄── Blob Storage (legacy 10-Ks)
             │                                     ▲
             ▼                                     │ borrower list
   Lakehouse Federation ──► Azure SQL (legacy): restricted_list · analyst_portfolio · borrowers
                 │
  2. Version {text, citations[quote, exact offsets], reasoning, trace, grounded}
                 ▼
  Analyst: review → feedback/quote → regenerate → time travel → approve
  Credit Portal: "Save approved sections to memo" → UPDATE memo_sections (portal-owned write)

  Audit dashboard (Databricks AI/BI): gateway usage + inference tables + refusals ──► MRM, Compliance
```

### 7.2 What changes, component by component

| Area | Legacy | Integrated | Owner |
| --- | --- | --- | --- |
| Ingestion | Function downloads 10-Ks to Blob | Function unchanged. A **Lakeflow job** reads the new files from Blob (Unity Catalog volume / external location), chunks and embeds them into the Delta table, and the index syncs | FDE → Sam |
| Borrower scope | Hardcoded tickers in the POC | `borrowers` read from Azure SQL through **Lakehouse Federation** (a foreign catalog) | FDE → Sam |
| Agent access | Streamlit only | Agent exposed as a **REST API**; the portal calls it with a service principal (OAuth M2M) and passes the analyst's email | FDE |
| Information barriers | Policy only | New **guard node**: refuses if the borrower is on `restricted_list` or not in the analyst's `analyst_portfolio` (read live through federation) | FDE → Aisha signs off |
| Memo writing | Copy-paste | **"Save to memo"** in the portal writes the cited draft to `memo_sections`. The portal owns the write; the agent never writes to the legacy DB | Elena |
| Audit and monitoring | None | Gateway usage + inference tables + refusal log → **AI/BI dashboard** for MRM and Compliance | FDE → Jordan, Aisha |
| Secrets | Key Vault | Same Key Vault; CD reads the Groq key at deploy time | Unchanged |

### 7.3 Integration contract: the AI Credit Memo Draft API

Implemented in `src/policypilot/memo/api.py`. The portal calls it with a service principal
and passes the signed-in analyst.

| Endpoint | Purpose |
| --- | --- |
| `GET /ai/drafts/{memo_id}?analyst=` | Workspace: memo, source filing, access check, the six sections with their state and version list |
| `POST /ai/drafts/{memo_id}/sections/{section}/generate` | One agent run → a new version. Body: `analyst_email`, optional `feedback`, `quotes` (exact excerpts with offsets), `base_version` |
| `POST .../sections/{section}/edit` | Analyst's own text → a new *human* version (surviving `[n]` markers keep their sources) |
| `GET .../sections/{section}/versions/{n}` | Any past version, with full trace (time travel) |
| `POST .../sections/{section}/current` | Make an older or newer version the working version again |
| `POST .../sections/{section}/approve` | Approve one specific version |
| `POST .../sections/{section}/saved` | Portal confirms it wrote that version into the legacy memo |
| `GET /ai/drafts/{memo_id}/events` | Audit trail: every run, refusal, restore, approval and save |

A version looks like this (abridged):

```json
{
  "version_no": 2, "origin": "ai", "based_on": 1,
  "feedback": "Lead with total debt and the maturity profile.",
  "quotes": [{"text": "...", "start": 81234, "end": 81390, "line_start": 1657, "line_end": 1657}],
  "text": "The company had $X of commercial paper outstanding [1] ...",
  "citations": [{"n": 1, "source": "S3", "quote": "...", "verified": true,
                 "start": 81234, "end": 81301, "line_start": 1657, "line_end": 1657}],
  "reasoning": "Relied on S3 (liquidity section) because ... Addressed the feedback by ...",
  "trace": {"guard": {...}, "queries": [...], "sources": [...], "model": "...", "latency_ms": 4210},
  "grounded": true, "refusal_reason": null
}
```

`refusal_reason` is one of `restricted_borrower` and `not_in_portfolio` (both returned as
HTTP 403 before any model call), or `no_grounded_answer`.

### 7.4 Design principles

- **The legacy system stays the system of record.** The agent reads; the portal writes.
- **Defense in depth:** the portal hides restricted borrowers, and the guard node blocks
  them again.
- **Human in the loop:** the AI drafts memo sections; the analyst edits and saves; the
  credit officer approves.
- **No new secrets in the legacy app:** the portal holds only a Databricks service
  principal identity; the LLM key stays behind Unity AI Gateway.

### 7.5 AI Credit Memo Draft: human-in-the-loop design

The integration adds exactly one tab to the Credit Portal. All other tabs, the layout, theme
and colours are unchanged.

- **Six independent runs.** Each memo section (business overview, industry, financial
  performance, liquidity and debt, key risks, legal and regulatory) is drafted by its own agent
  run with its own search plan. One weak section never contaminates the others, and each
  can be redone on its own.
- **Verified citations.** Every `[n]` carries a verbatim quote. The verify step only accepts
  a citation if the quote is found word for word in the cited passage. It then maps the quote
  to exact character and line positions in the filing.
- **Observability per answer.** For every version the analyst sees the citations (with
  "Open in document", which highlights the exact sentence in the filing), the AI's reasoning,
  the search plan, every retrieved passage with its score, and run details (model, latency,
  access check, raw model output).
- **Feedback loop.** A feedback box per section takes free text plus excerpts the analyst
  selects in the filing. Quoted excerpts are pinned into the next run's sources, and the
  previous draft is passed in so the model revises rather than starts over.
- **Time travel.** Every run, edit and restore appends an immutable version. The analyst can
  step through older and newer versions and make any of them the working version again.
- **Approval gate.** Nothing reaches the credit memo until the analyst approves a specific
  version and clicks "Save approved sections to memo". The portal then performs the write.

## 8. Engagement plan

About 8 weeks. Each phase ends with a meeting and circulated documents.

| Week | Phase | Activities | Meeting (role-play) | Documents circulated | Exit criteria |
| --- | --- | --- | --- | --- | --- |
| 1 | **Kickoff** | Agree goals, scope, access | Kickoff (Priya, Marcus, Elena, Sam, Jordan, Aisha, Tom) | Engagement charter | Access granted; stakeholders named |
| 1–2 | **Discovery** | Shadow analysts; walk through the portal, DB and Function; interview MRM and Compliance | Discovery workshops: business, technical, risk | Discovery notes; current-state architecture; problem statement and success metrics | Sponsor agrees the problem statement |
| 2 | **Proposal** | Options analysis; target design; security review | Solution review with leads and developers | Solution proposal (options A–D); security and data-flow review | Option D approved; POC scope agreed |
| 3–4 | **POC** | Build and evaluate PolicyPilot | POC demo and sign-off | POC plan; POC results and evaluation report | §6.2 criteria met |
| 5–7 | **Integration** | Federation, Lakeflow job, Ask API, guard node, portal panel, audit dashboard | Integration design review; weekly standups; go/no-go | Integration design (incl. API contract); test and UAT plan; deployment runbook | UAT passed; MRM validation pack submitted |
| 8 | **Handover** | Train users and the platform team; hypercare | Go-live; retro and handover | Operations runbook; user guide; handover note | Sam's team owns operations |

## 9. Document register

| Document | Audience | Phase | Status |
| --- | --- | --- | --- |
| Engagement charter | Client + internal | Kickoff | To write |
| Discovery notes | Internal | Discovery | To write |
| Current-state architecture | Client | Discovery | Draft in §3 |
| Problem statement and success metrics | Client | Discovery | Draft in §4 |
| Solution proposal | Client | Proposal | Draft in §5 |
| Security and data-flow review | Client (InfoSec) | Proposal | To write |
| POC plan and results report | Client | POC | To write (eval numbers from the harness) |
| Integration design | Client + internal | Integration | Draft in §7 |
| Test and UAT plan | Client | Integration | To write |
| MRM validation pack | Client (MRM) | Integration | To write |
| Deployment runbook | Internal + platform team | Integration | Exists: [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) |
| Operations runbook and user guide | Client | Handover | To write |

## 10. Meeting role-plays

Each meeting has a built-in tension. Resolving it is what interviewers want to hear about.

| Meeting | Attendees | Goal | Tension to resolve |
| --- | --- | --- | --- |
| Kickoff | All | Align on scope and success | Sponsor wants the whole credit workflow automated; FDE narrows it to drafting cited sections |
| Discovery: business | Marcus, analysts | Understand the memo workflow | Analysts don't trust AI after public-chatbot hallucinations |
| Discovery: technical | Elena, Sam | Map the legacy system | Elena refuses any new write path into Azure SQL |
| Discovery: risk | Jordan, Aisha, Tom | Collect governance requirements | MRM: "an LLM can't be validated"; Compliance: information barriers |
| Solution review | Leads and developers | Choose option D | Buy (B) vs build (D); cost of running Databricks |
| POC demo | Priya, Marcus, Jordan, Tom | Sign-off | MRM asks how groundedness is measured; InfoSec asks where the key lives |
| Integration design review | Elena, Sam, Aisha | Agree the contract | Who owns writes (portal); how the restricted list stays live (federation) |
| Go/no-go | All | Launch decision | One UAT defect open; agree to launch with mitigation |
| Retro and handover | Sam's team, Marcus | Transfer ownership | Avoiding long-term dependency on the FDE |

## 11. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Hallucinated memo content | Citation gate, refusal on uncited answers, analyst review before saving |
| Data leakage to the LLM provider | Only filing text (public data) goes to the LLM; key behind Unity AI Gateway; provider reviewed by InfoSec |
| Information-barrier breach | Guard node plus portal filtering; refusals logged for Compliance |
| MRM approval delays | Evaluation harness from day one; validation pack produced during integration |
| Beta platform features (for example Unity AI Gateway service policies) unavailable | Guardrails implemented in the agent (guard node); gateway policies added later |
| Legacy change freeze | Only additive changes to the portal (a new panel); the Function is untouched |
| Cost of always-on services | Vector Search and app compute sized small; teardown runbook for non-prod |

## 12. Interview talking points

- **Discovery before code:** "I shadowed analysts and found the real blocker was MRM and
  Compliance, not model quality."
- **Narrowing scope:** "We drafted cited memo sections instead of automating credit
  decisions, because that's what could pass model risk review."
- **Governance as a feature:** "Citations gave MRM explainability, the evaluation harness
  gave validation evidence, and the gateway logs gave Compliance an audit trail."
- **Respecting the legacy owner:** "The portal kept ownership of every database write; the
  agent was read-only."
- **Handover:** "Success meant the bank's platform team could run it without me."

## 13. Course build plan

| Step | What gets built | Azure / Databricks services |
| --- | --- | --- |
| 1 | **Legacy system:** Credit Portal, Azure SQL schema and seed data, nightly downloader Function, Blob container | App Service, Azure SQL (serverless), Azure Functions, Blob Storage |
| 2 | **POC:** PolicyPilot (already built) | Databricks, Unity Catalog, Vector Search, Unity AI Gateway, Databricks Apps |
| 3 | **Integration:** federation, Lakeflow ingestion from Blob, Ask API, guard node, portal panel and "Save to memo", audit dashboard | Lakehouse Federation, Lakeflow Jobs, Databricks Apps or Model Serving, AI/BI dashboards |

Keep costs down: Azure SQL serverless auto-pauses, the Function uses the consumption plan,
and App Service can use a basic tier. Tear down Vector Search and app compute after each
recording session.
