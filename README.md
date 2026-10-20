# Contoso Bank × PolicyPilot — Integrated System

> **Branch `integrated`** of a three-branch forward-deployed-engineering (FDE) project:
>
> | Branch | What it is |
> | --- | --- |
> | [`legacy`](../../tree/legacy) | Contoso Bank's existing Credit Portal (React + FastAPI), before any AI |
> | [`poc`](../../tree/poc) | PolicyPilot: the governed, cited 10-K Q&A agent built as the proof of concept |
> | **`integrated`** | The POC integrated into the Credit Portal as an **AI Credit Memo Draft** tab |
>
> The engagement story (client, stakeholders, problem statement, phases, meetings) is in
> [docs/fde/FDE_ENGAGEMENT_PLAN.md](docs/fde/FDE_ENGAGEMENT_PLAN.md). Contoso Bank and its
> people are fictional; the 10-K filings are real SEC data.

## What the integration adds

One new tab in the legacy Credit Portal. Every other tab, the layout and the theme are unchanged.

- **Six agent runs, one per credit memo section.** Each run is guard → plan → retrieve →
  draft → verify (`src/policypilot/memo/agent.py`).
- **Verified, clickable citations.** Every `[n]` carries a verbatim quote that is checked
  word for word against the filing. "Open in document" shows the filing with that exact
  sentence highlighted.
- **Observability for every answer:** citations, the AI's reasoning, the search plan, the
  retrieved passages with scores, and run details (model, latency, access check, raw output).
- **Human in the loop:** per-section feedback (free text plus excerpts quoted from the
  filing), regenerate, edit by hand, **time travel** across versions, and approve. Approved
  sections are written into the legacy memo by the portal itself.
- **Compliance guard:** restricted borrowers and borrowers outside the analyst's portfolio
  are refused before any model call, and the refusal is logged.
- **Single sign-on, enforced server-side:** both APIs take the user's identity only from a
  validated bearer token (no user picker, no user fields in requests).
- **The Credit Portal stays the source of truth for users and roles.** Its Administration tab
  (Portal Administrator: `e.novak@contoso.example`) grants access, changes roles and deactivates
  users. The AI service asks the portal (`GET /api/me`, with the user's own token) for the
  user's role on every request, so admin changes apply to the AI immediately. Unity Catalog
  governs the AI service's own access to data and models on Databricks.
- **Role-aware AI tab:** preparing analysts draft their own memos; Credit Officers and
  Compliance get a read-only review of the AI provenance; the Portal Administrator doesn't
  see the tab.

## Run the integrated system locally

Three processes. Put a valid `GROQ_API_KEY` in `.env` first.

```bash
# 1. Legacy Credit Portal API (port 8100) - first run: seed + download the 10-Ks
cd legacy/backend && uv sync && uv run python -m app.seed && uv run python -m app.jobs.download_filings
uv run uvicorn app.main:app --port 8100
```

```bash
# 2. AI Credit Memo Draft service (port 8200), from the repo root
uv sync --extra dev
uv run uvicorn policypilot.memo.api:app --port 8200
```

```bash
# 3. Credit Portal UI (port 5173), proxies /api -> 8100 and /ai -> 8200
cd legacy/frontend && npm install && npm run dev
```

Open http://localhost:5173 and sign in through the development identity provider (it stands in
for Microsoft Entra ID locally) as `m.lee@contoso.example`, password `contoso-dev`. Then go to
**AI Credit Memo Draft** → open `CM-2026-0101` (Apple) → **Draft all 6 sections**. The first
run on a filing also indexes it (about 20 seconds). Sign in as `p.raman@contoso.example`
(Credit Officer) to see the read-only review. All test accounts are listed in the `legacy`
branch README.

Tests: `uv run pytest` (root, includes the memo agent and API) and `cd legacy/backend && uv run pytest`.

---

# The POC: PolicyPilot

A governed regulatory/policy Q&A copilot — the first of three portfolio projects
demonstrating agentic AI patterns on Databricks + Azure (Q&A, AI reviewer, generation).
PolicyPilot answers questions about SEC 10-K filings and cites the filing every claim
came from, refusing rather than guessing when it can't ground an answer.

## Status

**Milestone 1 done: local prototype.** Real SEC EDGAR filings, a local Chroma vector
store, Llama (via Groq) as the LLM, and a Streamlit UI — all runnable on a laptop with
no cloud account.

**Milestone 2 done: deployed and verified on real Azure Databricks.** Workspace, Unity
Catalog, Key Vault, GitHub OIDC federation, and a live Databricks App were all stood up
and end-to-end tested — a real deployed question got a grounded, cited answer straight
from Apple's actual 10-K, served via a Databricks-hosted Vector Search index. The
Vector Search endpoint and app compute were torn down afterward to stop billing (they
bill by the hour; everything else — workspace, UC catalog/table, Key Vault, OIDC setup —
stays up at near-zero cost). See **[docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)**
for the full step-by-step (including every error hit and how to avoid it) to redo this
end to end.

**Milestone 3 in progress: guardrails, broader data, CI-gated eval** (see
[docs/UPGRADE_PLAN.md](docs/UPGRADE_PLAN.md)). Code-complete: ~20-ticker ingestion, LLM-based
ticker/company detection in `plan_node`, a Databricks Agent Evaluation harness gated in
`ci.yml`, and Unity Gateway in front of Groq (`resources/ai_gateway.yml`: a model provider
service + model service, deployed by the bundle along with their grants). Only the
guardrails are a manual one-time UI step — see [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)
Parts 6–7.

The code is structured so that swapping backends is a config change, not a rewrite (see
[Architecture](#architecture) below).

## Architecture

| Layer | Local | Databricks/Azure |
|---|---|---|
| Vector store | `retrieval/local_chroma.py` (Chroma + sentence-transformers) | `retrieval/databricks_vector_search.py` — Vector Search over `policypilot_dev.filings.chunks` (implemented, endpoint/index not created yet) |
| LLM | `agent/llm.py` `GroqLLMClient`, key from `.env` — guardrail-free by design (dev sandbox) | `DatabricksGatewayLLMClient` calling the `<catalog>.filings.gpt-oss` Unity Gateway model service (`resources/ai_gateway.yml`), which routes to Groq through a provider service holding the key, with guardrails — no raw Groq key in the App's env anymore, see [docs/UPGRADE_PLAN.md](docs/UPGRADE_PLAN.md) |
| Structured lookup | `ingestion/manifest.py` (local JSON) | UC Function over a Delta table (not built yet) |
| UI | `streamlit run` locally | Databricks App (`resources/apps.yml` + `app.yaml`, deploys the whole repo since the app imports the full `policypilot` package) |
| Ingestion | `python -m policypilot.ingestion.pipeline` | `notebooks/seed_chunks_table.py` (manual, self-contained) |

Switch backends via `PP_ENV` (`local` or `databricks`). The agent itself
(`agent/graph.py`, a LangGraph plan → retrieve → answer → verify loop) never changes —
it only talks to the `VectorStore` and `LLMClient` protocols in `retrieval/base.py` and
`agent/llm.py`.

### Deferred: not Mosaic AI yet

Databricks' "Mosaic AI" branding covers Agent Framework (log an agent to Unity Catalog
via MLflow, deploy behind Model Serving), Agent Evaluation, and Agent Bricks. This
project uses Agent Evaluation (CI-gated, see below) and Unity AI Gateway (governance for
the Groq call) but not the rest — the agent itself still runs as plain LangGraph, not
logged to UC or served behind Model Serving. Full Foundation Model migration (swapping
Groq for a Databricks-native model) was deliberately reversed — see
[docs/UPGRADE_PLAN.md](docs/UPGRADE_PLAN.md) item 3 — since a Unity Gateway model service in
front of Groq provides the same guardrails without a provider migration.

The agent is deliberately not a bare RAG chain: `verify_node` is a hard citation gate —
an answer with no `[n]` citation back to retrieved context is replaced with a refusal
before it reaches the user.

## Local setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
uv sync --extra dev
cp .env.example .env
# edit .env and set GROQ_API_KEY
```

### 1. Ingest filings

Pulls the latest 10-K for ~20 large-cap tickers (`DEFAULT_TICKERS` in `config.py`) from
SEC EDGAR (public, no auth), chunks them, embeds them locally, and stores them in
`data/chroma/`.

```bash
uv run python -m policypilot.ingestion.pipeline
```

### 2. Run the chat UI

```bash
uv run streamlit run src/policypilot/app/streamlit_app.py
```

### 3. Run the eval harness

Runs the golden question set (~47 questions across all ingested tickers, plus one
deliberately off-corpus question to check the refusal gate) through the agent via
Databricks Agent Evaluation (`mlflow.genai.evaluate`, `mlflow[databricks]>=3.1`). The
hosted judges (safety, relevance, retrieval groundedness) need Databricks workspace auth;
the citation-presence check runs locally either way.

```bash
uv sync --extra dev --extra eval
uv run python -m policypilot.eval.agent_eval
```

### Tests

```bash
uv run pytest
uv run ruff check .
```

## Next steps

Done: Azure Databricks workspace (Central India, Premium, Serverless), Unity Catalog
(`policypilot_dev.filings.chunks`), Key Vault + AKV-backed secret scope holding the
Groq key. `databricks.yml`'s `dev` target already points at the real workspace host.

Remaining, in order — the last three are deliberately batched into one short session
since Vector Search/Model Serving endpoints cost money while running:

1. **GitHub OIDC federation**: an Entra ID app registration + federated credential
   trusting this repo + a role assignment on `policypilot-rg`, then
   `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` / `DATABRICKS_HOST`
   as GitHub environment secrets. No ongoing cost.
2. **Seed real data**: run `notebooks/seed_chunks_table.py` in the workspace to populate
   `policypilot_dev.filings.chunks`.
3. **Create a Vector Search endpoint** and a Delta-Sync index over
   `policypilot_dev.filings.chunks` (self-managed embeddings, `embedding` column) —
   `DatabricksVectorSearchStore` is already implemented against it.
4. **Deploy**: trigger `.github/workflows/cd.yml` (GitHub Actions "Run workflow" button
   — runs `databricks bundle deploy` on GitHub's runner, no local CLI needed) to push
   the Databricks App.
5. **Test end-to-end**, then delete the Vector Search endpoint and stop the App to stop
   the meter.

## Repo layout

```
src/policypilot/
├── config.py               # env-driven settings, local vs. databricks backend selection
├── ingestion/               # SEC EDGAR fetch -> chunk -> embed -> store
├── retrieval/                # VectorStore protocol + local/Databricks implementations
├── agent/                    # LLM client protocol, tools, LangGraph agent
├── eval/                     # golden dataset + Databricks Agent Evaluation harness
└── app/                       # Streamlit chat UI (becomes the Databricks App)
notebooks/seed_chunks_table.py # Self-contained: fetch+chunk+embed+write into UC, run in-workspace
scripts/setup_unity_catalog.py # UC provisioning script (dev catalog was created by hand instead)
resources/, databricks.yml     # Databricks Asset Bundle (deploy config)
app.yaml, requirements.txt     # Databricks App runtime config (repo root, since app.yml deploys the whole repo)
.github/workflows/              # CI (active) + CD (manual-dispatch, until GitHub OIDC is wired up)
```
