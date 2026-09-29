# PolicyPilot — Project Description

## One-liner

> A governed, agentic Q&A copilot over SEC 10-K filings, deployed end to end on Azure
> Databricks. Every answer cites the filing it came from, or the agent refuses.

## Short description

**PolicyPilot** is a governed, agentic Q&A copilot for regulatory filings. Ask it about
any of 20 large companies, such as *"What supply chain risks does Apple disclose?"*, and
it answers from their latest SEC 10-K with a numbered citation for every claim. If it
can't ground an answer in the filing, it refuses instead of guessing. It's built as a
LangGraph agent and deployed on Azure Databricks: Unity Catalog governs the data, Vector
Search handles retrieval, Unity Gateway sits in front of the LLM, and it's served as a
Databricks App. GitHub Actions deploys it with no stored cloud credentials.

## What it does

- Answers natural-language questions about the latest 10-K filings of 20 large-cap
  companies (Apple, Microsoft, JPMorgan, Nvidia and others), pulled live from SEC EDGAR.
- Cites every factual sentence as `[1]`, `[2]` and shows a **Sources** panel that maps
  each citation to the company, filing date and accession number.
- Refuses when it can't ground an answer, for example off-topic questions or
  information missing from the filing.

## How the agent works

A LangGraph state machine: `plan → retrieve → answer → verify`.

| Step | What happens |
| --- | --- |
| **Plan** | An LLM rewrites the question into a search query and resolves the company, by name or ticker, to one of the 20 known tickers. |
| **Retrieve** | Vector search **limited to the resolved company's filing**, so near-identical boilerplate from other companies' 10-Ks can't leak into the answer. |
| **Answer** | The LLM answers only from the retrieved context, with a strict `[n]` citation format. |
| **Verify** | A code check (not a prompt) replaces any uncited answer with a refusal. |

## Platform: Azure Databricks

- **Unity Catalog:** the chunk embeddings live in a Delta table with Change Data Feed
  enabled.
- **Vector Search:** a Delta Sync index using self-managed 384-dim embeddings
  (`all-MiniLM-L6-v2`), so local and cloud retrieval use the same embedding model.
- **Unity Gateway:** the app calls Groq's `gpt-oss-120b` through a Unity Catalog
  **model service** backed by a **model provider service**. The app never holds the API
  key, and access is controlled with Unity Catalog `EXECUTE` grants.
- **Databricks Apps:** the Streamlit UI runs under its own least-privilege service
  principal.

## Delivery and security

- **Databricks Asset Bundles:** the app, the gateway provider and model service, and
  their grants, are all declared in YAML.
- **GitHub Actions with OIDC federation:** no Azure credentials are stored in GitHub. At
  deploy time, CD reads the LLM key straight from **Azure Key Vault**, and the key never
  touches git.
- **CI:** Ruff and pytest (with a fake LLM, so no API key is needed), plus a Databricks
  Agent Evaluation job that scores safety, relevance and groundedness against a golden
  question set.
- **Two backends:** `PP_ENV=local` runs Chroma and calls Groq directly on a laptop, and
  `PP_ENV=databricks` uses the Databricks stack above. The same agent code runs in both.

## Tech stack

Python · LangGraph · Groq (`gpt-oss-120b`) · sentence-transformers · ChromaDB · Streamlit ·
Azure Databricks (Unity Catalog, Vector Search, Unity Gateway, Databricks Apps, Asset
Bundles, Agent Evaluation) · Azure Key Vault · Microsoft Entra ID · GitHub Actions (OIDC)

## More

- Step-by-step build and deployment runbook, including every error hit along the way:
  [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- Local setup and repo layout: [../README.md](../README.md)
