# Databricks notebook source
# MAGIC %md
# MAGIC # Seed policypilot_dev.filings.chunks
# MAGIC Self-contained: fetches the latest 10-K for a few tickers from SEC EDGAR (public,
# MAGIC no auth), chunks + embeds them, and writes into the UC table so the Vector Search
# MAGIC Delta-Sync index has real rows to sync. Deliberately doesn't import the `policypilot`
# MAGIC package (avoids any bundle-sync/path uncertainty during a timed live session) —
# MAGIC mirrors ingestion/{edgar_client,chunker}.py but standalone.

# COMMAND ----------
%pip install -q requests beautifulsoup4 sentence-transformers
dbutils.library.restartPython()

# COMMAND ----------
import time

import requests
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer

CATALOG = "policypilot_dev"
SCHEMA = "filings"
TABLE = f"{CATALOG}.{SCHEMA}.chunks"
TICKERS = ["AAPL", "MSFT", "JPM"]
USER_AGENT = "PolicyPilot research prototype yashstudy02@gmail.com"  # SEC requires a real contact
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def get(url: str):
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    time.sleep(0.15)
    return resp


def get_cik(ticker: str) -> int:
    data = get("https://www.sec.gov/files/company_tickers.json").json()
    for entry in data.values():
        if entry["ticker"] == ticker.upper():
            return int(entry["cik_str"])
    raise ValueError(f"No CIK for {ticker}")


def get_recent_10k(cik: int) -> dict:
    data = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
    recent = data["filings"]["recent"]
    for i, form in enumerate(recent["form"]):
        if form == "10-K":
            return {
                "cik": cik,
                "accession_number": recent["accessionNumber"][i],
                "primary_document": recent["primaryDocument"][i],
                "filing_date": recent["filingDate"][i],
                "company": data.get("name", str(cik)),
            }
    raise ValueError(f"No 10-K for CIK {cik}")


def download_text(filing: dict) -> str:
    accession_nodash = filing["accession_number"].replace("-", "")
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{filing['cik']}/"
        f"{accession_nodash}/{filing['primary_document']}"
    )
    html = get(url).text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text(separator="\n").splitlines()]
    return "\n".join(line for line in lines if line)


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks, start = [], 0
    while start < len(words):
        chunks.append(" ".join(words[start : start + chunk_size]))
        if start + chunk_size >= len(words):
            break
        start += chunk_size - overlap
    return chunks


# COMMAND ----------
embedder = SentenceTransformer(EMBEDDING_MODEL)
rows = []

for ticker in TICKERS:
    cik = get_cik(ticker)
    filing = get_recent_10k(cik)
    text = download_text(filing)
    chunks = chunk_text(text)
    embeddings = embedder.encode(chunks, show_progress_bar=False).tolist()
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
        rows.append(
            {
                "chunk_id": f"{ticker}-{filing['accession_number']}-{i}",
                "ticker": ticker,
                "company": filing["company"],
                "filing_date": filing["filing_date"],
                "accession_number": filing["accession_number"],
                "chunk_index": i,
                "text": chunk,
                "embedding": embedding,
            }
        )
    print(f"{ticker}: {len(chunks)} chunks")

print(f"Total: {len(rows)} chunks across {len(TICKERS)} tickers")

# COMMAND ----------
df = spark.createDataFrame(rows)
df.write.mode("append").saveAsTable(TABLE)
display(spark.sql(f"SELECT ticker, company, filing_date, count(*) AS n_chunks FROM {TABLE} GROUP BY ALL"))
