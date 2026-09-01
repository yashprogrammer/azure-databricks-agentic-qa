"""Environment-driven configuration. Picks local vs. Databricks backends via PP_ENV."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CHROMA_DIR = DATA_DIR / "chroma"

# A handful of large, well-known filers — enough real filings to build and test
# retrieval without pulling the whole EDGAR corpus.
DEFAULT_TICKERS = ["AAPL", "MSFT", "JPM"]

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
GROQ_MODEL = "openai/gpt-oss-120b"

# Unity Catalog / Vector Search resource names — must match whatever's actually
# provisioned in the workspace (see README "Next steps").
UC_CATALOG = "policypilot_dev"
UC_SCHEMA = "filings"
UC_CHUNKS_TABLE = f"{UC_CATALOG}.{UC_SCHEMA}.chunks"
VECTOR_SEARCH_ENDPOINT = "policypilot-vs-endpoint"
VECTOR_SEARCH_INDEX = f"{UC_CATALOG}.{UC_SCHEMA}.chunks_index"


@dataclass(frozen=True)
class Settings:
    env: str
    groq_api_key: str | None
    sec_user_agent: str
    databricks_host: str | None
    databricks_token: str | None

    @property
    def is_local(self) -> bool:
        return self.env == "local"


def get_settings() -> Settings:
    return Settings(
        env=os.environ.get("PP_ENV", "local"),
        groq_api_key=os.environ.get("GROQ_API_KEY") or None,
        sec_user_agent=os.environ.get(
            "SEC_EDGAR_USER_AGENT", "PolicyPilot research prototype (no contact set)"
        ),
        databricks_host=os.environ.get("DATABRICKS_HOST") or None,
        databricks_token=os.environ.get("DATABRICKS_TOKEN") or None,
    )
