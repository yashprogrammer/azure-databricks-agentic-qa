# PolicyPilot

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

The code is structured so that swapping backends is a config change, not a rewrite (see
[Architecture](#architecture) below).

## Architecture

| Layer | Local | Databricks/Azure |
|---|---|---|
| Vector store | `retrieval/local_chroma.py` (Chroma + sentence-transformers) | `retrieval/databricks_vector_search.py` — Vector Search over `policypilot_dev.filings.chunks` (implemented, endpoint/index not created yet) |
| LLM | `agent/llm.py` `GroqLLMClient`, key from `.env` | Same `GroqLLMClient`, key injected from the `policypilot-kv-scope` secret scope as `GROQ_API_KEY` — see [Deferred](#deferred-not-mosaic-ai-yet) |
| Structured lookup | `ingestion/manifest.py` (local JSON) | UC Function over a Delta table (not built yet) |
| UI | `streamlit run` locally | Databricks App (`resources/apps.yml` + `app.yaml`, deploys the whole repo since the app imports the full `policypilot` package) |
| Ingestion | `python -m policypilot.ingestion.pipeline` | `notebooks/seed_chunks_table.py` (manual, self-contained) now; `resources/jobs.yml` Lakeflow job later |

Switch backends via `PP_ENV` (`local` or `databricks`). The agent itself
(`agent/graph.py`, a LangGraph plan → retrieve → answer → verify loop) never changes —
it only talks to the `VectorStore` and `LLMClient` protocols in `retrieval/base.py` and
`agent/llm.py`.

### Deferred: not Mosaic AI yet

Databricks' "Mosaic AI" branding covers Agent Framework (log an agent to Unity Catalog
via MLflow, deploy behind Model Serving), Agent Evaluation, and Agent Bricks. This
project doesn't use it yet — the agent runs as plain LangGraph calling Groq directly,
even once deployed as a Databricks App. Adopting Mosaic AI Agent Framework (MLflow-log
the agent in UC, serve it behind Model Serving, optionally swap Groq for a Foundation
Model API or an Azure OpenAI External Model behind Unity AI Gateway) is a deliberate
future step, not required for the agent to work end-to-end on Databricks.

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

Pulls the latest 10-K for AAPL, MSFT, and JPM from SEC EDGAR (public, no auth), chunks
them, embeds them locally, and stores them in `data/chroma/`.

```bash
uv run python -m policypilot.ingestion.pipeline
```

### 2. Run the chat UI

```bash
uv run streamlit run src/policypilot/app/streamlit_app.py
```

### 3. Run the eval harness

Runs the golden question set (including one deliberately off-corpus question, to check
the refusal gate) through the agent and scores groundedness + citation presence, logged
to a local MLflow run (`mlflow ui` to view).

```bash
uv run python -m policypilot.eval.run_eval
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
├── eval/                     # golden dataset + MLflow eval harness
└── app/                       # Streamlit chat UI (becomes the Databricks App)
notebooks/seed_chunks_table.py # Self-contained: fetch+chunk+embed+write into UC, run in-workspace
scripts/setup_unity_catalog.py # UC provisioning script (dev catalog was created by hand instead)
resources/, databricks.yml     # Databricks Asset Bundle (deploy config)
app.yaml, requirements.txt     # Databricks App runtime config (repo root, since app.yml deploys the whole repo)
.github/workflows/              # CI (active) + CD (manual-dispatch, until GitHub OIDC is wired up)
```
