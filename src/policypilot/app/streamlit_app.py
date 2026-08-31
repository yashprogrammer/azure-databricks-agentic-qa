"""PolicyPilot chat UI. Local: `streamlit run src/policypilot/app/streamlit_app.py`.
In production this becomes the Databricks App (see resources/apps.yml) — same code,
deployed behind an app service principal with on-behalf-of-user auth.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from policypilot.agent.graph import ask
from policypilot.agent.llm import get_llm_client
from policypilot.config import DEFAULT_TICKERS, get_settings
from policypilot.ingestion.pipeline import get_vector_store

st.set_page_config(page_title="PolicyPilot", page_icon="📄")
st.title("📄 PolicyPilot")
st.caption(
    "Governed Q&A over SEC 10-K filings — every answer cites the filing it came from, "
    "or refuses if it can't."
)


@st.cache_resource
def _load_backend():
    settings = get_settings()
    if not settings.groq_api_key:
        return None, None, settings
    return get_llm_client(), get_vector_store(), settings


llm, store, settings = _load_backend()

with st.sidebar:
    st.subheader("Corpus")
    st.write(f"Tickers ingested: {', '.join(DEFAULT_TICKERS)}")
    st.caption("Run `uv run python -m policypilot.ingestion.pipeline` to (re)ingest.")
    st.subheader("Backend")
    st.write(f"PP_ENV = `{settings.env}`")

if llm is None:
    st.error(
        "GROQ_API_KEY is not set. Copy .env.example to .env and add your key, then restart."
    )
    st.stop()

if "history" not in st.session_state:
    st.session_state.history = []

for role, content in st.session_state.history:
    with st.chat_message(role):
        st.markdown(content)

if question := st.chat_input("Ask a question about the ingested filings..."):
    st.session_state.history.append(("user", question))
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving and answering..."):
            result = ask(llm, store, question)
        answer = result["final_answer"]
        st.markdown(answer)
        if not result.get("grounded"):
            st.caption("⚠️ No grounded citation found — refused rather than guessing.")
    st.session_state.history.append(("assistant", answer))
