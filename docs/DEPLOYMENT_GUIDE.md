# PolicyPilot: Complete Build Guide — Local Prototype → Real Databricks/Azure Deployment

This is a start-to-finish runbook for building PolicyPilot (a governed Q&A agent over SEC
10-K filings) and deploying it for real on Azure Databricks. It's written from an actual
build session, including every error we hit and exactly how to avoid or fix it — follow it
in order and you shouldn't hit the same walls.

**Format:** each Part is a phase you can film as one segment. ⚠️ callouts are gotchas that
cost us real time — don't skip them.

---

## Architecture at a glance

```
Local dev                          Databricks/Azure (production)
──────────                         ──────────────────────────────
Chroma (local vector store)   →    Unity Catalog Delta table + Vector Search index
Groq API (direct)             →    Same Groq API, key from Key Vault-backed secret scope
Streamlit (laptop)             →    Databricks App (same code, deployed)
Local JSON manifest            →    (same, or a UC table later)
```

The agent itself (LangGraph: plan → retrieve → answer → verify) never changes. Only the
`VectorStore` and `LLMClient` backends swap, via a `PP_ENV` env var (`local` vs
`databricks`).

**Cost note:** the workspace, Unity Catalog, and Key Vault cost near-nothing at rest.
**Vector Search endpoints and Databricks App compute bill by the hour while running** —
provision them last, test, then tear down (Part 12).

---

## Part 0 — Prerequisites

- Azure subscription (any tier; a fresh "pay-as-you-go" is fine)
- GitHub account, `gh` CLI installed and authenticated (`gh auth login`)
- Local: Python 3.11+, [`uv`](https://docs.astral.sh/uv/)
- A [Groq API key](https://console.groq.com) (free tier is enough) — **check
  `client.models.list()` before hardcoding a model name.**
  ⚠️ We hardcoded `llama-3.3-70b-versatile` and got `model_not_found` — that model wasn't
  available on the account's key. List available models first and pick one that exists,
  e.g. `openai/gpt-oss-120b`.

---

## Part 1 — Local project scaffold

Build and fully test this locally before touching Azure. Nothing here costs money.

### 1.1 Structure

```
pyproject.toml, uv.lock, .gitignore, .env.example, README.md
databricks.yml
resources/{jobs.yml,apps.yml}
app.yaml, requirements.txt          # Databricks App runtime config (repo root — see 5.2)
src/policypilot/
├── config.py                       # env-driven settings, resource-name constants
├── ingestion/{edgar_client,chunker,pipeline,manifest}.py
├── retrieval/{base,local_chroma,databricks_vector_search}.py
├── agent/{llm,tools,graph}.py
├── eval/{golden_dataset.jsonl,run_eval}.py
└── app/streamlit_app.py
scripts/setup_unity_catalog.py
notebooks/seed_chunks_table.py
tests/
```

### 1.2 `pyproject.toml`

Standard `uv`-managed project. Key dependency gotcha:

⚠️ **The PyPI package is `databricks-vectorsearch`, not `databricks-vector-search`.** The
latter doesn't exist and will fail `uv sync` with "No solution found." The import path is
still `from databricks.vector_search.client import VectorSearchClient` (it's a compat
shim over the renamed `databricks-ai-search` package internally — don't worry about that,
just get the pip name right).

```toml
dependencies = [
    "groq>=0.13.0", "langgraph>=0.2.60", "mlflow>=2.18.0", "chromadb>=0.5.20",
    "sentence-transformers>=3.3.0", "streamlit>=1.40.0", "requests>=2.32.0",
    "python-dotenv>=1.0.1", "beautifulsoup4>=4.12.3", "pydantic>=2.9.0", "pandas>=2.2.0",
]
[project.optional-dependencies]
databricks = ["databricks-sdk>=0.36.0", "databricks-vectorsearch>=0.40"]
dev = ["pytest>=8.3.0", "ruff>=0.8.0"]
```

Run `uv sync --extra dev` to install.

### 1.3 SEC EDGAR ingestion

⚠️ **SEC blocks generic User-Agents with a 403.** A placeholder like
`"MyApp research prototype"` gets rejected; you need a real contact:

```python
SEC_EDGAR_USER_AGENT = "PolicyPilot research prototype you@example.com"
```

Client hits three public, unauthenticated endpoints:
- `https://www.sec.gov/files/company_tickers.json` — ticker → CIK lookup
- `https://data.sec.gov/submissions/CIK{cik:010d}.json` — filing list, find latest `10-K`
- `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{doc}` — the filing
  itself (strip HTML with BeautifulSoup)

Chunk with a simple word-window splitter (~1200 words, 200 overlap) — good enough for a
10-K.

### 1.4 Retrieval — local backend

`LocalChromaVectorStore`: `chromadb.PersistentClient` + `sentence-transformers`
(`all-MiniLM-L6-v2`, 384-dim, no API key needed). This is what you develop against.

### 1.5 Agent (LangGraph)

Four nodes: `plan` (LLM turns the question into a search query) → `retrieve` (vector
search + optional structured lookup) → `answer` (LLM answers *only* from retrieved
context) → `verify` (hard citation gate).

⚠️ **Ticker-detection bug**: don't do this —
```python
for word in question.upper().split():   # BUG: uppercases everything first,
    if word == word.upper(): ...        # so this check always passes!
```
Match against your known ticker list instead:
```python
words = {w.strip(".,?!").upper() for w in question.split()}
ticker_hint = next((t for t in KNOWN_TICKERS if t in words), None)
```

⚠️ **Weak citation prompting**: a vague instruction like "cite sources" gets ignored by
smaller open models. Be explicit and give an example:
```
This is a strict citation requirement: every sentence containing a factual claim MUST
end with a bracketed citation number like [1] or [2] — no other citation style (no
footnotes, no parentheses). Example: 'The filing discloses X [1].'
```
Then gate on it in code: `re.search(r"\[\d+\]", answer)` — if it doesn't match, replace
the answer with a refusal rather than showing an uncited response.

### 1.6 LLM client

Keep it simple: one `GroqLLMClient`, used in both local and Databricks environments (see
Part 10 for why we didn't bother with a "native Databricks model" path — Groq works fine
called from inside Databricks too, once auth is wired correctly).

### 1.7 Eval harness

⚠️ **`mlflow.log_table(data=rows, ...)` rejects a list of dicts** — "data must be a
pandas.DataFrame or a dictionary." Wrap it: `mlflow.log_table(data=pd.DataFrame(rows), ...)`.

Include at least one deliberately off-corpus question (e.g. "what's the capital of
France?") in your golden set — it's the cheapest way to verify the refusal gate actually
fires, not just that citations look nice on relevant questions.

### 1.8 Test locally before going further

```bash
uv run ruff check .
uv run pytest
uv run python -m policypilot.ingestion.pipeline      # real SEC filings, local Chroma
uv run streamlit run src/policypilot/app/streamlit_app.py --server.port 8600
uv run python -m policypilot.eval.run_eval
```
Don't proceed to Azure until this all works end to end locally.

---

## Part 2 — Push to GitHub

```bash
git init
git add -A && git commit -m "Initial scaffold"
gh repo create <your-repo-name> --public --source=. --push
```

---

## Part 3 — Azure Portal: provisioning (all GUI, no CLI needed)

Do this in the browser at [portal.azure.com](https://portal.azure.com). No `az` CLI
required for any of this.

### 3.1 Set a budget + alert first

**Cost Management + Billing → Budgets → + Add.** Scope it to your subscription, set a
monthly amount you're comfortable with, add alert thresholds (50/80/100%) with your email.
Do this *before* creating anything else — it's your safety net.

### 3.2 Resource group

**Resource groups → + Create.** Pick a name (e.g. `policypilot-rg`) and region.

### 3.3 Azure Databricks workspace

**Azure Databricks → + Create.**
- **Pricing Tier: Premium** (required — Standard doesn't support Unity Catalog or
  Key Vault-backed secret scopes)
- **Workspace type: Serverless** (no VNet/storage account setup needed; matches how
  Databricks Apps and Vector Search run anyway)
- Leave Networking/Encryption/Security & compliance tabs at defaults (all the CMK/
  compliance-profile toggles are enterprise add-ons, several irreversible once enabled —
  skip them for a dev build)

Deploy takes a few minutes. Click **"Go to resource" → "Launch Workspace."**

### 3.4 Verify Unity Catalog

Open **Catalog Explorer** — Databricks now auto-provisions a UC metastore for new
workspaces in most regions. You should see at least one catalog already listed.

### 3.5 Create your catalog/schema/table

In Catalog Explorer, **"+ Create Catalog"** (name it, e.g. `policypilot_dev`, Databricks-
managed storage). Inside it, **"+ Create schema"** (e.g. `filings`). Then open **SQL
Editor**, create a small serverless SQL warehouse if prompted (2X-Small, auto-stop 10 min
— cheapest option, fine for this), and run:

```sql
CREATE TABLE IF NOT EXISTS policypilot_dev.filings.chunks (
    chunk_id STRING NOT NULL, ticker STRING, company STRING, filing_date STRING,
    accession_number STRING, chunk_index INT, text STRING, embedding ARRAY<FLOAT>
)
USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true)   -- required for Vector Search sync
```

### 3.6 Azure Key Vault

**Key vaults → + Create.** Standard tier. On the **Access configuration** tab:

⚠️ **Pick "Vault access policy", not "Azure role-based access control."** Databricks'
AKV-backed secret scopes specifically require the legacy access-policy permission model —
RBAC-only vaults can't be linked.

### 3.7 Add your secret

In the vault, **Objects → Secrets → + Generate/Import**. Name: `groq-api-key`. Value:
your Groq key.

### 3.8 Link the vault to Databricks as a secret scope

This page isn't in the normal nav — it's a hidden URL:

```
https://<your-workspace-url>/#secrets/createScope
```

Fill in: **Scope Name** (e.g. `policypilot-kv-scope`), **Manage Principal: Creator**,
**DNS Name**: `https://<your-vault-name>.vault.azure.net/`, **Resource ID**: from the
vault's Properties tab (`/subscriptions/.../resourceGroups/.../providers/Microsoft.KeyVault/vaults/...`).

### 3.9 Verify

New notebook, run:
```python
dbutils.secrets.listScopes()                       # should show your scope
dbutils.secrets.list("policypilot-kv-scope")        # should show groq-api-key
```

---

## Part 4 — GitHub OIDC federation (no stored Azure secrets in GitHub)

### 4.1 Entra ID app registration

**Azure Portal → App registrations → + New registration.** Name it (e.g.
`<project>-github-oidc`), Single tenant, no redirect URI. **Register.** Copy the
**Application (client) ID** and **Directory (tenant) ID** from the Overview page.

### 4.2 Federated credential

**Certificates & secrets → Federated credentials → + Add credential →** scenario
**"GitHub Actions deploying Azure resources."**

⚠️ **Azure now requires immutable numeric GitHub org/repo IDs**, not just names. Get them:
```bash
gh api users/<your-github-org-or-username> --jq .id
gh api repos/<owner>/<repo> --jq .id
```

⚠️ **Entity type must be "Environment", not "Branch"** — *if* your deploy workflow
declares a GitHub `environment:` (which it should, see Part 5.5). GitHub's OIDC subject
claim is `repo:org:environment:<name>` when a job specifies an environment, which
overrides the branch-based subject. Set:
- **Organization**: your GitHub org/username + its numeric ID
- **Repository**: repo name + its numeric ID
- **Entity type**: **Environment**
- **GitHub environment name**: `dev` (matching what you'll create in step 4.5)
- Leave Audience as default (`api://AzureADTokenExchange`)

### 4.3 Role assignment on the resource group

**Resource group → Access control (IAM) → + Add → Add role assignment.**

⚠️ **Plain "Contributor" is under the "Privileged administrator roles" tab**, not "Job
function roles" — searching "Contributor" in the default tab surfaces dozens of
`*Contributor` roles but not the base one. Switch tabs first.

Assign it to your app registration (search by the name from 4.1).

### 4.4 GitHub environment + secrets

```bash
gh api --method PUT repos/<owner>/<repo>/environments/dev
gh secret set AZURE_CLIENT_ID --env dev --repo <owner>/<repo> --body "<client-id>"
gh secret set AZURE_TENANT_ID --env dev --repo <owner>/<repo> --body "<tenant-id>"
gh secret set AZURE_SUBSCRIPTION_ID --env dev --repo <owner>/<repo> --body "<sub-id>"
gh secret set DATABRICKS_HOST --env dev --repo <owner>/<repo> --body "https://<workspace-url>"
```

### 4.5 ⚠️ CRITICAL: Azure RBAC ≠ Databricks permissions

Contributor-on-the-resource-group only lets this identity manage the *Azure ARM resource*
(the workspace object itself) — it has **zero permission to do anything inside
Databricks** (create jobs, deploy apps, touch Unity Catalog). This is a separate identity
system. You must **also**:

1. In the Databricks workspace: profile icon → **Settings → Identity and access →
   Service principals (Manage) → Add service principal.**
2. Choose **"Microsoft Entra ID managed"** (not "Databricks managed") — link by the
   **Application ID** from 4.1. Give it Workspace access + Databricks SQL access.
3. Grant it Unity Catalog permissions (run in SQL Editor, using its Application ID as
   the principal):
```sql
GRANT USE CATALOG ON CATALOG policypilot_dev TO `<app-client-id>`;
GRANT USE SCHEMA ON SCHEMA policypilot_dev.filings TO `<app-client-id>`;
GRANT SELECT, MODIFY ON TABLE policypilot_dev.filings.chunks TO `<app-client-id>`;
```

---

## Part 5 — Databricks Asset Bundle (DAB) files

### 5.1 `databricks.yml`

```yaml
bundle:
  name: policypilot
include:
  - resources/apps.yml
  # jobs.yml excluded until its placeholders are filled in — see 5.4
variables:
  catalog:
    default: policypilot
targets:
  dev:
    mode: development
    default: true
    workspace:
      host: https://<your-workspace-url>
      root_path: /Workspace/Users/${workspace.current_user.userName}/.bundle/${bundle.name}/${bundle.target}
    variables:
      catalog: policypilot_dev
```

### 5.2 `resources/apps.yml`

⚠️ **`source_code_path` must point at your repo root, not just the `app/` subfolder** —
if your Streamlit file imports the rest of your package (`from policypilot.agent.graph
import ask`), deploying only the `app/` folder breaks that import at runtime.

```yaml
resources:
  apps:
    policypilot_app:
      name: policypilot
      source_code_path: ..    # repo root, relative to resources/apps.yml
      resources:
        - name: groq-key
          secret:
            scope: policypilot-kv-scope
            key: groq-api-key
            permission: READ
```

### 5.3 `app.yaml` + `requirements.txt` (repo root)

Because 5.2 deploys the whole repo, these live at the repo root, not inside `app/`:

```yaml
# app.yaml
command: ["streamlit", "run", "src/policypilot/app/streamlit_app.py"]
env:
  - name: "PP_ENV"
    value: "databricks"
  - name: "GROQ_API_KEY"
    valueFrom: "groq-key"
```

`requirements.txt` — Databricks Apps can't read `pyproject.toml`, so mirror your
dependencies by hand here.

### 5.4 `resources/jobs.yml`

If you haven't wired up the ingestion job yet (cluster ID, alert email still
placeholders), **don't include it in `databricks.yml`** — a bundle deploy will try to
validate/create it and fail on the placeholder values. Add it back once filled in.

### 5.5 `.github/workflows/cd.yml`

```yaml
on:
  workflow_dispatch:
    inputs:
      target:
        default: dev
permissions:
  id-token: write
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ inputs.target }}   # <-- this is what makes OIDC subject = "environment:dev"
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - uses: databricks/setup-cli@main
      - run: databricks bundle validate -t ${{ inputs.target }}
        env: { DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }} }
      - run: databricks bundle deploy -t ${{ inputs.target }}
        env: { DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }} }
```

---

## Part 6 — First deploy attempt (and the secret-permission gotcha)

Trigger it: **GitHub repo → Actions → CD workflow → Run workflow** (branch `main`,
target `dev`).

⚠️ **Expect this failure the first time:**
```
Error: cannot create resources.apps.policypilot_app: User does not have permission to
add resource groq-key to app policypilot. User needs MANAGE permission on the resource.
(403 PERMISSION_DENIED)
```
This is a real, correct security guardrail — the *deploying* identity (your GitHub OIDC
service principal) can't bind a secret it doesn't control, even though it's a valid
secret in a scope you own. Fix it once:

1. Generate a short-lived Databricks PAT (profile → Settings → Developer → Access
   tokens → Generate new token — scope it to what's needed, e.g. "secrets"/"workspace").
2. Grant the deploying SP MANAGE permission on the scope (no clean GUI for this — use
   the REST API):
```bash
curl -X POST "https://<workspace-url>/api/2.0/secrets/acls/put" \
  -H "Authorization: Bearer <your-pat>" -H "Content-Type: application/json" \
  -d '{"scope": "policypilot-kv-scope", "principal": "<deploying-sp-app-id>", "permission": "MANAGE"}'
```
3. Re-run the GitHub Actions workflow — it should now succeed all the way through
   ("Validate bundle" → "Deploy bundle" both green).

---

## Part 7 — Actually starting the app

⚠️ **`databricks bundle deploy` only *registers* the app config — it does not start
compute or deploy your source code.** You'll see the app exists in Databricks Apps UI but
in a `STOPPED`/`UNAVAILABLE` state. Two more calls are needed (can run these via `curl`
with your PAT, or click "Start"/"Deploy" in the Apps UI):

```bash
# 1. Start compute
curl -X POST "https://<workspace-url>/api/2.0/apps/<app-name>/start" -H "Authorization: Bearer <pat>"

# 2. Find where the bundle uploaded your source (root_path from databricks.yml,
#    under the deploying SP's Workspace user folder)
curl "https://<workspace-url>/api/2.0/workspace/list?path=/Workspace/Users/<deploying-sp-app-id>/.bundle/<bundle-name>/<target>/files" \
  -H "Authorization: Bearer <pat>"

# 3. Deploy the source
curl -X POST "https://<workspace-url>/api/2.0/apps/<app-name>/deployments" \
  -H "Authorization: Bearer <pat>" -H "Content-Type: application/json" \
  -d '{"source_code_path": "<path-from-step-2>"}'
```
Poll `GET /api/2.0/apps/<app-name>/deployments/<deployment-id>` until `state: SUCCEEDED`.

---

## Part 8 — Vector Search endpoint + index

**Do this last, right before you're ready to test** — it starts billing immediately.

### 8.1 Create the endpoint

Catalog Explorer → your `chunks` table → **Create → "AI Search index"** (current name for
Vector Search) → on the create-index form, click **"Create an endpoint"** → name it,
**Type: Standard** (fine for small datasets).

### 8.2 Create the index

- **Primary key**: `chunk_id`
- **Embedding source**: **"Use existing embeddings"** (you already computed them with
  sentence-transformers locally — don't let Databricks recompute with a different model,
  the dimensions/semantics would mismatch your local dev setup)
- **Embedding vector column**: `embedding`, **dimension**: `384` (for `all-MiniLM-L6-v2`)
- **Index update mode**: **Triggered** (not Continuous — Continuous needs always-on
  compute and costs more; you don't need real-time sync for a demo)

### 8.3 ⚠️ If it hangs on "Provisioning resources... / Waiting for initial sync..."

Check the pipeline's actual error (Data Ingest section → click the Pipeline id link, or
via API: `GET /api/2.0/pipelines/<pipeline-id>/events`). We hit this exact error on a
fresh endpoint's very first index:
```
Error: Response Code: 404 ... "Index policypilot_dev.filings.chunks_index does not exist"
```
This is a backend propagation race on the endpoint's first-ever index — it'll keep
auto-retrying and keep failing identically. **Fix: delete the index and recreate it with
the same settings.** The second creation registers cleanly:
```bash
curl -X DELETE ".../api/2.0/vector-search/indexes/<catalog>.<schema>.<index>" -H "Authorization: Bearer <pat>"
# then recreate via the UI, or POST /api/2.0/vector-search/indexes with the same spec
```

### 8.4 Verify

`GET /api/2.0/vector-search/indexes/<full-index-name>` → `status.detailed_state` should
reach `ONLINE_NO_PENDING_UPDATE`, `ready: true`, `indexed_row_count` matching your table's
row count.

---

## Part 9 — Seed real data into the table

If your ingestion job isn't wired up yet, run a self-contained notebook instead
(`notebooks/seed_chunks_table.py` in this repo) — it fetches from SEC EDGAR, chunks,
embeds with the same local model, and writes into the UC table with plain PySpark, no
dependency on your package being importable in the workspace. Paste it into a new
Databricks notebook, run top to bottom. Expect 2-4 minutes (serverless cold-start +
model download + embedding).

---

## Part 10 — Databricks App runtime fixes (code-level)

These three errors only appear once the app is actually *running* on Databricks — you
can't catch them locally. Fix all three before testing, or expect to iterate.

### 10.1 `InvalidInputException: Please specify either personal access token or service principal client ID and secret.`

`VectorSearchClient()`'s no-args auto-detection uses MLflow's *notebook*-context
resolver — it doesn't work inside a Databricks App process (a plain Python/Streamlit
process, not a notebook). Fix: pass credentials explicitly. Databricks Apps auto-inject
`DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` as env vars for the
app's own service principal — read and pass them:

```python
import os
client = VectorSearchClient(
    workspace_url=os.environ.get("DATABRICKS_HOST"),
    service_principal_client_id=os.environ.get("DATABRICKS_CLIENT_ID"),
    service_principal_client_secret=os.environ.get("DATABRICKS_CLIENT_SECRET"),
)
```

### 10.2 `requests.exceptions.MissingSchema: Invalid URL 'adb-xxxx.azuredatabricks.net/oidc/v1/token'`

The injected `DATABRICKS_HOST` is a **bare hostname**, no `https://` prefix. Fix:
```python
host = os.environ.get("DATABRICKS_HOST")
if host and not host.startswith("http"):
    host = f"https://{host}"
```

### 10.3 `PermissionDenied: Insufficient permissions for UC entity <catalog>.<schema>.<index>`

⚠️ **The deployed app runs under its own, separate, auto-created service principal**
(shown in the Databricks Apps UI, e.g. `app-xxxxx <app-name>`) — **different from the
GitHub OIDC deploying SP you granted permissions to in Part 4.5.** It needs its own
grants:

```sql
GRANT USE CATALOG ON CATALOG policypilot_dev TO `<app-own-sp-client-id>`;
GRANT USE SCHEMA ON SCHEMA policypilot_dev.filings TO `<app-own-sp-client-id>`;
GRANT SELECT, MODIFY ON TABLE policypilot_dev.filings.chunks TO `<app-own-sp-client-id>`;
GRANT SELECT ON TABLE policypilot_dev.filings.chunks_index TO `<app-own-sp-client-id>`;
```
Plus, Vector Search endpoints have their own separate permission model on top of UC
grants — grant `CAN_USE`:
```bash
curl -X PATCH ".../api/2.0/permissions/vector-search-endpoints/<endpoint-id>" \
  -H "Authorization: Bearer <pat>" -H "Content-Type: application/json" \
  -d '{"access_control_list": [{"service_principal_name": "<app-own-sp-client-id>", "permission_level": "CAN_USE"}]}'
```
Find the app's own SP client ID via `GET /api/2.0/apps/<app-name>` →
`service_principal_client_id`. Find the endpoint ID via the endpoint's Overview page or
`GET /api/2.0/vector-search/endpoints/<endpoint-name>`.

After fixing 10.1-10.3, redeploy (Part 7, steps 2-3 — re-upload via a fresh
`databricks bundle deploy` if you changed code, then re-trigger the app deployment).

---

## Part 11 — Test end to end

Open the app URL (from `GET /api/2.0/apps/<app-name>` → `url`, or the Databricks Apps
UI). It needs your Databricks SSO session, so open it in a browser where you're already
logged into the workspace. Ask a real question about one of your ingested companies and
confirm you get a cited, grounded answer (`[1]`, `[2]` referencing real filing text).

---

## Part 12 — Teardown (stop the meter)

Once you've verified it works, tear down anything that bills by the hour:

```bash
curl -X POST ".../api/2.0/apps/<app-name>/stop" -H "Authorization: Bearer <pat>"
curl -X DELETE ".../api/2.0/vector-search/indexes/<full-index-name>" -H "Authorization: Bearer <pat>"
curl -X DELETE ".../api/2.0/vector-search/endpoints/<endpoint-name>" -H "Authorization: Bearer <pat>"
```

**What's safe to leave running (near-zero cost):** the workspace itself, Unity Catalog
catalog/schema/table (your seeded data stays), Key Vault + secret scope, the GitHub OIDC
setup, the SQL warehouse (auto-stops after idle timeout). Next time you want to demo,
you only need to redo Part 8 (recreate the endpoint + index) and Part 7 (start + deploy
the app) — everything else is already there.

Also: revoke the temporary PAT you generated in Part 6 (Settings → Developer → Access
tokens → delete it) once you're done — it was only needed for the one-time secret-ACL
grant.

---

## Appendix: every error, one line each

| # | Error | Fix |
|---|---|---|
| 1 | SEC EDGAR 403 Forbidden | Use a real-contact User-Agent from the start |
| 2 | Groq `model_not_found` | Call `client.models.list()` first, don't hardcode |
| 3 | Ticker-detection always matches | Match against known tickers, not `word == word.upper()` after uppercasing the whole string |
| 4 | Model won't produce `[1]`-style citations | Explicit strict prompt + example, code-level regex gate |
| 5 | `mlflow.log_table` TypeError | Pass a `pandas.DataFrame`, not a list of dicts |
| 6 | `uv sync` can't find `databricks-vector-search` | Real package name is `databricks-vectorsearch` |
| 7 | Streamlit app `ImportError` on Databricks | `source_code_path` must be repo root, not just `app/` |
| 8 | Bundle validate fails on job placeholders | Exclude `jobs.yml` from `include:` until filled in |
| 9 | Azure "Contributor" role missing from list | It's under "Privileged administrator roles" tab, not "Job function roles" |
| 10 | Federated credential subject mismatch | Entity type = "Environment" (matching `environment:` in the workflow), not "Branch" |
| 11 | Azure RBAC doesn't grant Databricks access | Separately add the SP as a Databricks service principal + UC grants |
| 12 | "User needs MANAGE permission on resource groq-key" | Grant the deploying SP MANAGE on the secret scope via `secrets/acls/put` |
| 13 | App stuck `STOPPED` after bundle deploy | `bundle deploy` doesn't start/deploy apps — call `/start` then `/deployments` explicitly |
| 14 | Vector Search index stuck provisioning | First-index race condition — delete and recreate the index |
| 15 | `InvalidInputException` in deployed app | Pass `DATABRICKS_HOST`/`CLIENT_ID`/`CLIENT_SECRET` explicitly, auto-detection doesn't work in Apps |
| 16 | `MissingSchema` on OIDC token URL | `DATABRICKS_HOST` env var has no `https://` — prepend it |
| 17 | `PermissionDenied` on UC entity from the running app | The app has its OWN service principal — grant it UC + Vector Search endpoint permissions separately from the deploy SP |
