"""Eval harness: runs the golden dataset through the agent, scores each answer for
groundedness (LLM-judge) and citation presence (code scorer), logs results to MLflow.

The golden set deliberately includes one off-corpus question ("capital of France") to
verify the refusal gate actually fires on ungrounded questions, not just cite on-topic ones.
"""

from __future__ import annotations

import json
import re

import mlflow
import pandas as pd

from policypilot.agent.graph import CITATION_RE, ask
from policypilot.agent.llm import get_llm_client
from policypilot.config import REPO_ROOT, get_settings
from policypilot.ingestion.pipeline import get_vector_store

GOLDEN_PATH = REPO_ROOT / "src" / "policypilot" / "eval" / "golden_dataset.jsonl"

JUDGE_SYSTEM_PROMPT = (
    "You are grading whether an AI assistant's answer is fully grounded in the provided "
    "context. Score 1 if every claim in the answer is supported by the context (or the "
    "assistant correctly refused due to insufficient context), 0 if the answer contains "
    "claims not supported by the context. Reply with ONLY the digit 0 or 1."
)


def load_golden_dataset() -> list[dict]:
    return [json.loads(line) for line in GOLDEN_PATH.read_text().splitlines() if line.strip()]


def judge_groundedness(llm, context: str, answer: str) -> int:
    prompt = f"Context:\n{context}\n\nAnswer:\n{answer}"
    verdict = llm.complete(
        system=JUDGE_SYSTEM_PROMPT, messages=[{"role": "user", "content": prompt}]
    )
    match = re.search(r"[01]", verdict)
    return int(match.group()) if match else 0


def run_eval() -> dict:
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set — required to run the agent and the judge."
        )

    llm = get_llm_client()
    store = get_vector_store()
    dataset = load_golden_dataset()

    mlflow.set_experiment("policypilot-eval")
    rows = []
    with mlflow.start_run(run_name="golden-dataset-eval"):
        for item in dataset:
            result = ask(llm, store, item["question"])
            answer = result["final_answer"]
            context = "\n".join(r.text for r in result.get("results", []))
            citation_present = bool(CITATION_RE.search(answer))
            groundedness = judge_groundedness(llm, context, answer)
            rows.append(
                {
                    "ticker": item.get("ticker"),
                    "question": item["question"],
                    "answer": answer,
                    "grounded_gate_passed": result.get("grounded", False),
                    "citation_present": citation_present,
                    "groundedness_judge": groundedness,
                }
            )

        citation_rate = sum(r["citation_present"] for r in rows) / len(rows)
        groundedness_rate = sum(r["groundedness_judge"] for r in rows) / len(rows)

        mlflow.log_param("num_questions", len(rows))
        mlflow.log_metric("citation_rate", citation_rate)
        mlflow.log_metric("groundedness_rate", groundedness_rate)
        mlflow.log_table(data=pd.DataFrame(rows), artifact_file="eval_results.json")

        print(f"\nQuestions evaluated: {len(rows)}")
        print(f"Citation rate:      {citation_rate:.0%}")
        print(f"Groundedness rate:  {groundedness_rate:.0%}\n")
        for r in rows:
            flag = "OK" if r["groundedness_judge"] else "FAIL"
            print(f"[{flag}] {r['question']}")

    return {"citation_rate": citation_rate, "groundedness_rate": groundedness_rate, "rows": rows}


if __name__ == "__main__":
    run_eval()
