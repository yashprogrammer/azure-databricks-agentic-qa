"""One-time Unity Catalog setup for PolicyPilot. NOT runnable yet — requires a real
Databricks workspace + Unity Catalog metastore (DATABRICKS_HOST / DATABRICKS_TOKEN in .env).

Creates, idempotently:
  - catalog `policypilot`
  - schema  `policypilot.filings`
  - volume  `policypilot.filings.raw_documents` (landing zone for source PDFs/HTML)
  - table   `policypilot.filings.chunks` (Delta, CDC-enabled for Vector Search sync)

Run once against each target (dev/staging/prod) after provisioning:
    uv run python scripts/setup_unity_catalog.py
"""

from __future__ import annotations

from policypilot.config import get_settings

CATALOG = "policypilot"
SCHEMA = "filings"
CHUNKS_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.chunks (
    chunk_id STRING NOT NULL,
    ticker STRING,
    company STRING,
    filing_date STRING,
    accession_number STRING,
    chunk_index INT,
    text STRING,
    embedding ARRAY<FLOAT>
)
USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true)
"""


def main() -> None:
    settings = get_settings()
    if not settings.databricks_host or not settings.databricks_token:
        raise RuntimeError(
            "DATABRICKS_HOST and DATABRICKS_TOKEN must be set in .env before running this "
            "script. This project has no Databricks workspace provisioned yet — see the "
            "README 'Next steps' checklist."
        )

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient(host=settings.databricks_host, token=settings.databricks_token)
    warehouse_id = _require_warehouse(w)

    print(f"Creating catalog {CATALOG} (if not exists)...")
    w.statement_execution.execute_statement(
        statement=f"CREATE CATALOG IF NOT EXISTS {CATALOG}", warehouse_id=warehouse_id
    )
    print(f"Creating schema {CATALOG}.{SCHEMA} (if not exists)...")
    w.statement_execution.execute_statement(
        statement=f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}", warehouse_id=warehouse_id
    )
    print(f"Creating volume {CATALOG}.{SCHEMA}.raw_documents (if not exists)...")
    w.statement_execution.execute_statement(
        statement=f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_documents",
        warehouse_id=warehouse_id,
    )
    print(f"Creating table {CATALOG}.{SCHEMA}.chunks (if not exists)...")
    w.statement_execution.execute_statement(statement=CHUNKS_TABLE_DDL, warehouse_id=warehouse_id)
    print("Unity Catalog setup complete.")


def _require_warehouse(w) -> str:
    warehouses = list(w.warehouses.list())
    if not warehouses:
        raise RuntimeError("No SQL warehouse found in this workspace — create one first.")
    return warehouses[0].id


if __name__ == "__main__":
    main()
