# PolicyPilot

A governed regulatory/policy Q&A copilot — the first of three portfolio projects
demonstrating agentic AI patterns on Databricks + Azure (Q&A, AI reviewer, generation).
PolicyPilot answers questions about SEC 10-K filings and cites the filing every claim
came from, refusing rather than guessing when it can't ground an answer.

## Status

**Milestone 1 (current): local prototype + cloud-ready scaffold.** No Azure Databricks
workspace is provisioned yet, so everything here runs locally — real SEC EDGAR filings,
a local Chroma vector store, Llama via the Groq API directly, and a Streamlit UI.
The code is structured so that swapping to Databricks Vector Search, Unity Catalog,
Model Serving, and Databricks Apps is a config change, not a rewrite (see
[Architecture](#architecture) below).

## Architecture

| Layer | Local (now) | Databricks/Azure (next) |
|---|---|---|
| Vector store | `retrieval/local_chroma.py` (Chroma + sentence-transformers) | `retrieval/databricks_vector_search.py` — Vector Search over a UC Delta table |
| LLM | `agent/llm.py` `GroqLLMClient` (direct API) | `agent/llm.py` `DatabricksModelServingClient` (behind Unity AI Gateway) |
| Structured lookup | `ingestion/manifest.py` (local JSON) | UC Function over a Delta table |
| UI | `streamlit run` locally | Databricks App (`resources/apps.yml`) |
| Ingestion | `python -m policypilot.ingestion.pipeline` | Lakeflow Job (`resources/jobs.yml`), same `run_ingestion()` |

Switch backends via `PP_ENV` in `.env` (`local` or `databricks`). The agent itself
(`agent/graph.py`, a LangGraph plan → retrieve → answer → verify loop) never changes —
it only talks to the `VectorStore` and `LLMClient` protocols in `retrieval/base.py` and
`agent/llm.py`.

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

## Next steps: going from local to Databricks/Azure

None of this has been done yet — it's the next session's work once you have (or want to
provision) an Azure subscription:

1. **Provision an Azure Databricks workspace** with Unity Catalog enabled (or use an
   existing one). Note the workspace URL.
2. **Create an Azure Key Vault** and an Azure Key Vault-backed secret scope in the
   workspace for the Groq/Azure OpenAI key and any source-system credentials
   (requires an Entra ID service principal with Contributor/Owner on the vault).
3. **Run `scripts/setup_unity_catalog.py`** against the new workspace to create the
   `policypilot` catalog/schema/volume/table.
4. **Create a Vector Search endpoint** and a Delta-sync index over
   `policypilot.filings.chunks`; implement `DatabricksVectorSearchStore` in
   `retrieval/databricks_vector_search.py` against it.
5. **Deploy an LLM** — either Databricks Foundation Model APIs or an Azure OpenAI
   External Model behind Unity AI Gateway — and implement `DatabricksModelServingClient`
   in `agent/llm.py`.
6. **Fill in `databricks.yml`** target hosts and run-as service principals, and
   `resources/jobs.yml` / `resources/apps.yml` placeholders (cluster ID, alert email).
7. **Set up GitHub OIDC**: create an Entra ID app registration with a federated
   credential trusting this repo, add `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` /
   `AZURE_SUBSCRIPTION_ID` / `DATABRICKS_HOST` as GitHub environment secrets (per target:
   dev/staging/prod), then switch `.github/workflows/cd.yml` from manual-dispatch-only to
   triggering on push to `main`.
8. **Deploy**: `databricks bundle validate -t dev` then `databricks bundle deploy -t dev`.

## Repo layout

```
src/policypilot/
├── config.py               # env-driven settings, local vs. databricks backend selection
├── ingestion/               # SEC EDGAR fetch -> chunk -> embed -> store
├── retrieval/                # VectorStore protocol + local/Databricks implementations
├── agent/                    # LLM client protocol, tools, LangGraph agent
├── eval/                     # golden dataset + MLflow eval harness
└── app/                       # Streamlit chat UI (becomes the Databricks App)
scripts/setup_unity_catalog.py # UC provisioning (run once against a real workspace)
resources/, databricks.yml     # Databricks Asset Bundle (deploy config)
.github/workflows/              # CI (active) + CD (manual-dispatch, inactive until Azure is wired up)
```
