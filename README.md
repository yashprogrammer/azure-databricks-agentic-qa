# Contoso Bank — Commercial Credit Portal (legacy system)

> **Branch `legacy`** of a three-branch FDE project. This branch is the client's existing
> system *before* any AI: `legacy` → [`poc`](../../tree/poc) → [`integrated`](../../tree/integrated).
> Contoso Bank and everyone in the seed data are fictional; the 10-K filings are real SEC data.

Credit analysts use this portal to review corporate borrowers once a year: they read the
borrower's 10-K in the Filing Library, search it by keyword, and write a six-section credit
memo that a credit officer approves.

| Component | Local (this repo) | Azure (later) |
| --- | --- | --- |
| Credit Portal UI | React + Vite (`legacy/frontend`) | App Service (static build) |
| Credit Portal API | FastAPI (`legacy/backend/app/main.py`) | App Service (Python) |
| Database | SQLite file (`legacy/backend/data/contoso.db`) | Azure SQL Database |
| Filing store | Folder (`legacy/backend/storage/filings/`) | Blob Storage container |
| Nightly filing download | `python -m app.jobs.download_filings` | Azure Function (timer trigger) |

## Known pain points (why the bank called in an FDE)

- Reading a 100–300 page 10-K per borrower is slow, and **keyword search misses meaning**:
  try searching Apple's filing for "revolving credit" (0 hits) vs. "commercial paper".
- The **Restricted List** is only a red warning flag; nothing stops research on a
  restricted borrower.
- No audit trail of who researched what.

## Run it locally

```bash
cd legacy/backend
uv sync --extra dev
uv run python -m app.seed                    # analysts, borrowers, portfolios, memos
uv run python -m app.jobs.download_filings   # downloads 20 real 10-Ks from SEC EDGAR (~1 min)
uv run uvicorn app.main:app --port 8100
```

```bash
cd legacy/frontend
npm install
npm run dev                                  # http://localhost:5173
```

## Sign-in, permissions and user administration

- **Who you are** comes only from a validated bearer token (RS256 JWT: signature, issuer,
  audience and expiry are checked). Locally a **development identity provider**
  (`app/dev_idp.py`, mounted at `/dev-idp`) plays the bank's employee directory and stands in for
  Microsoft Entra ID. Its tokens carry identity only, not roles.
- **What you may do** is the portal's own decision: the `analysts` table holds each user's
  portal role and whether their access is active (`app/auth.py`). It is read on every request,
  so changes apply immediately.
- **Portal Administrators** manage that table in the **Administration** tab: grant access to a
  directory employee, change roles, deactivate or reactivate users (`app/admin.py`). Changes are
  written to the activity log; an administrator cannot change or deactivate their own account.

Fictional employees in the development directory, all with the development password
`contoso-dev` (override with `DEV_IDP_PASSWORD`):

| User ID | Person | Portal role (seed) |
| --- | --- | --- |
| `m.lee@contoso.example` | Marcus Lee | Credit Analyst |
| `a.ruiz@contoso.example` | Ana Ruiz | Credit Analyst |
| `d.cho@contoso.example` | Daniel Cho | Credit Analyst |
| `p.raman@contoso.example` | Priya Raman | Credit Officer: approves or returns memos |
| `a.karim@contoso.example` | Aisha Karim | Compliance Reviewer: read-only |
| `e.novak@contoso.example` | Elena Novak | **Portal Administrator** |
| `g.kim@contoso.example` | Grace Kim | *no access*: a new joiner to grant access to |
| `j.blake@contoso.example`, `s.okafor@contoso.example`, `t.fischer@contoso.example` | Jordan Blake, Sam Okafor, Tom Fischer | *no access* |

Employees without portal access can sign in but are told their account is not set up.

On Azure, turn the development IdP off and point the API at Entra ID:

```bash
DEV_IDP_ENABLED=false
AUTH_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
AUTH_AUDIENCE=api://<credit-portal-api-client-id>
AUTH_JWKS_URL=https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys
```

Tests: `cd legacy/backend && uv run pytest`.
