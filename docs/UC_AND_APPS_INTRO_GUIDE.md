# Unity Catalog & Databricks Apps — Standalone Intro (No PolicyPilot Required)

A self-contained walkthrough for teaching Unity Catalog and Databricks Apps as general
concepts, independent of the PolicyPilot project. Uses a workspace you've already created
in Azure. Everything here is disposable — a toy `demo_catalog` and a toy app you can
delete when you're done.

**The two examples connect on purpose**: the sample app reads from the sample catalog, so
learners see the full loop (governed data → an app reading it) rather than two unrelated
demos. This also reuses the exact governance lesson from the main project, at a much
simpler scale — worth calling out explicitly when you get there.

---

## Part 1 — Unity Catalog

### What it is (the 60-second version for your audience)

- A **unified governance layer** for data and AI assets across a workspace (and across
  multiple workspaces, at the account level).
- Everything lives in a **three-level namespace**: `catalog.schema.object` — think of it
  like folders: catalog → schema → table (or volume, model, function...).
- It's where **permissions, audit logs, and lineage** live — `GRANT`/`REVOKE` statements
  control who (a person *or* a service principal) can see or touch what, and every access
  is logged.
- Before Unity Catalog, Databricks used a per-workspace "Hive Metastore" with no built-in
  fine-grained governance — UC is what replaced that with something enterprise-grade.

### Example: create a sample catalog, schema, and table

1. **Catalog Explorer** (left sidebar) → click the **"+"** icon → **"Create Catalog"**.
   - Name: `demo_catalog`
   - Storage: Databricks-managed (default) — no need for your own storage account
   - Create.
2. Inside `demo_catalog`, click **"+ Create schema"**.
   - Name: `demo_schema`
3. Open **SQL Editor** (left sidebar). If prompted, create a small serverless SQL
   warehouse (2X-Small is fine — cheap, auto-stops when idle).
4. Run this to create and populate a toy table:

```sql
CREATE TABLE demo_catalog.demo_schema.employees (
    id INT,
    name STRING,
    department STRING,
    salary DOUBLE
);

INSERT INTO demo_catalog.demo_schema.employees VALUES
  (1, 'Alice', 'Engineering', 95000),
  (2, 'Bob',   'Sales',       72000),
  (3, 'Carol', 'Marketing',   68000),
  (4, 'Dave',  'Engineering', 88000);

SELECT * FROM demo_catalog.demo_schema.employees;
```

5. Go back to **Catalog Explorer**, expand `demo_catalog` → `demo_schema` → `employees`,
   and click through the tabs — **Overview**, **Sample Data**, **Permissions** — to show
   learners what a governed table actually looks like from the outside: owner, schema,
   who currently has access (probably just you, right now).
6. **Make governance tangible** — grant a teammate (or a second test account) read access:

```sql
GRANT SELECT ON TABLE demo_catalog.demo_schema.employees TO `someone@example.com`;
```

That's the entire mental model: a namespaced object, with permissions attached directly
to it, enforced the same way regardless of whether a human or a robot is asking.

---

## Part 2 — Databricks Apps

### What it is (the 60-second version)

- A way to host a real interactive web app — Streamlit, Dash, Gradio, Flask (Python), or
  React/Express (Node) — **directly inside the workspace**, on Databricks-managed
  serverless compute.
- Users open it through their existing **Databricks SSO** session — no separate login
  system.
- Every app gets its **own dedicated, auto-created service principal** — a robot identity
  distinct from you, the developer, that the app uses to talk to Unity Catalog, SQL
  warehouses, etc. on its own behalf. This one detail is the source of almost every
  permission surprise you'll hit, so it's worth flagging early.

### Example: a tiny app that reads the catalog table you just made

1. **Compute** (left sidebar) → **Apps** tab → **Create app** (or **"+ New app"**).
2. Pick the **Streamlit** template (blank/custom is fine — you're going to replace the
   starter code anyway).
3. Name it something like `employee-directory-demo`.
4. It'll scaffold a small workspace folder with starter files (`app.py`,
   `requirements.txt`, `app.yaml`) and open a browser-based code editor. Replace
   `requirements.txt` with:

```
streamlit
databricks-sdk
```

5. Replace `app.py` with:

```python
import streamlit as st
from databricks.sdk import WorkspaceClient

st.set_page_config(page_title="Employee Directory Demo", page_icon="🗂️")
st.title("🗂️ Employee Directory")
st.caption("A minimal Databricks App reading live from a Unity Catalog table.")

WAREHOUSE_ID = "<YOUR_SQL_WAREHOUSE_ID>"  # copy from the SQL Warehouses page

w = WorkspaceClient()


@st.cache_data(ttl=30)
def load_employees():
    result = w.statement_execution.execute_statement(
        statement="SELECT * FROM demo_catalog.demo_schema.employees",
        warehouse_id=WAREHOUSE_ID,
    )
    columns = [c.name for c in result.manifest.schema.columns]
    rows = result.result.data_array or []
    return columns, rows


columns, rows = load_employees()
departments = ["All"] + sorted({row[2] for row in rows})
choice = st.selectbox("Filter by department", departments)

filtered = [r for r in rows if choice == "All" or r[2] == choice]
st.table([dict(zip(columns, r)) for r in filtered])
```

6. Click **Deploy** (or **Start** then **Deploy**, depending on the UI version — if it
   only registers the app without running it, that's the same "deploy vs. start" split
   as the real project: registering the config and actually running the code are two
   separate steps).
7. **⚠️ The governance callback moment**: open the app and it'll likely error with a
   permissions message — because the app's *own* service principal (shown on the app's
   details page, not your personal account) doesn't have any grants on `demo_catalog`
   yet. Fix it the same way as the main project, just simpler — no second "deploying SP"
   to worry about here, just this one:

```sql
GRANT USE CATALOG ON CATALOG demo_catalog TO `<app-service-principal-client-id>`;
GRANT USE SCHEMA ON SCHEMA demo_catalog.demo_schema TO `<app-service-principal-client-id>`;
GRANT SELECT ON TABLE demo_catalog.demo_schema.employees TO `<app-service-principal-client-id>`;
```

(You'll also want the app's service principal to have `CAN_USE` on the SQL warehouse
itself — check the warehouse's Permissions tab if the query still fails after the UC
grants.)

8. Refresh the app — it should now show the employee table with a working department
   filter, reading live from Unity Catalog.

**The punchline for your audience**: this exact "the app has its own identity, and that
identity needs its own grants" moment is the single most common surprise people hit with
Databricks Apps — and it's the same mechanism (just simpler) as the two-service-principal
gotcha in the full PolicyPilot deployment.

---

## Cleanup (after recording)

```sql
DROP TABLE demo_catalog.demo_schema.employees;
DROP SCHEMA demo_catalog.demo_schema;
DROP CATALOG demo_catalog;
```

Then delete the app from **Compute → Apps** (stops its compute and removes it). Neither
of these examples cost anything once torn down — the SQL warehouse auto-stops when idle,
and the app only bills while its compute is running.
