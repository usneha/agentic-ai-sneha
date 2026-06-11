"""
RAGAS evaluation: scores each (question, method) record in output/rag_eval.json
for the 5 SAMPLE_QUERIES against the golden reference answers in
output/golden_dataset.json, using faithfulness, answer relevancy, and context
recall.

Run from the repo root (requires OPENAI_API_KEY in .env):
    uv run python 4_retrieval/run_ragas_eval.py

Writes output/ragas_eval.json (per-record scores, written incrementally so a
crash mid-run doesn't lose completed records) and output/ragas_summary.csv
(mean per method, computed from successfully-scored records). Re-running skips
(question, method) pairs already present in output/ragas_eval.json.
"""

import asyncio
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

# Keep eval-script LangSmith traces separate from live chat traces
os.environ["LANGCHAIN_PROJECT"] = "course-rag-eval"

from openai import AsyncOpenAI

from langsmith.wrappers import wrap_openai
from ragas.embeddings import OpenAIEmbeddings
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, ContextRecall, Faithfulness

from run_retrieval import SAMPLE_QUERIES

JUDGE_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
MAX_RETRIES = 3
PER_RECORD_TIMEOUT = 240

OUTPUT_DIR = Path(__file__).parent.parent / "output"
RAG_EVAL_PATH = OUTPUT_DIR / "rag_eval.json"
GOLDEN_DATASET_PATH = OUTPUT_DIR / "golden_dataset.json"
RAGAS_EVAL_PATH = OUTPUT_DIR / "ragas_eval.json"
RAGAS_SUMMARY_PATH = OUTPUT_DIR / "ragas_summary.csv"

METRIC_NAMES = ["faithfulness", "answer_relevancy", "context_recall"]


async def score_record(record, reference, metrics):
    faithfulness, answer_relevancy, context_recall = metrics
    user_input = record["question"]
    response = record["answer"]
    retrieved_contexts = [chunk["chunk_text"] for chunk in record["chunks"]]

    for attempt in range(MAX_RETRIES):
        try:
            f, ar, cr = await asyncio.wait_for(
                asyncio.gather(
                    faithfulness.ascore(user_input=user_input, response=response, retrieved_contexts=retrieved_contexts),
                    answer_relevancy.ascore(user_input=user_input, response=response),
                    context_recall.ascore(user_input=user_input, retrieved_contexts=retrieved_contexts, reference=reference),
                ),
                timeout=PER_RECORD_TIMEOUT,
            )
            return {
                "question": user_input,
                "method": record["method"],
                "faithfulness": f.value,
                "answer_relevancy": ar.value,
                "context_recall": cr.value,
            }
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 15 * (attempt + 1)
            print(f"  [retry] {record['method']:18s} {user_input[:40]} -> {type(e).__name__}, waiting {wait}s", flush=True)
            await asyncio.sleep(wait)


def write_summary(results):
    sums = defaultdict(lambda: defaultdict(float))
    counts = defaultdict(int)
    for r in results:
        if any(r.get(m) is None for m in METRIC_NAMES):
            continue
        counts[r["method"]] += 1
        for m in METRIC_NAMES:
            sums[r["method"]][m] += r[m]

    with open(RAGAS_SUMMARY_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["method"] + METRIC_NAMES)
        for method, count in counts.items():
            writer.writerow([method] + [f"{sums[method][m] / count:.4f}" for m in METRIC_NAMES])

    print(f"Wrote summary to {RAGAS_SUMMARY_PATH}")


async def main():
    rag_eval = json.loads(RAG_EVAL_PATH.read_text())
    rag_eval = [r for r in rag_eval if r["question"] in SAMPLE_QUERIES]
    golden = {item["question"]: item["reference"] for item in json.loads(GOLDEN_DATASET_PATH.read_text())}

    results = json.loads(RAGAS_EVAL_PATH.read_text()) if RAGAS_EVAL_PATH.exists() else []
    done = {(r["question"], r["method"]) for r in results}
    todo = [r for r in rag_eval if (r["question"], r["method"]) not in done]

    print(f"{len(done)} records already scored, {len(todo)} remaining", flush=True)

    if todo:
        client = wrap_openai(AsyncOpenAI())
        llm = llm_factory(JUDGE_MODEL, client=client)
        embeddings = OpenAIEmbeddings(client=client, model=EMBEDDING_MODEL)
        metrics = (
            Faithfulness(llm=llm),
            AnswerRelevancy(llm=llm, embeddings=embeddings),
            ContextRecall(llm=llm),
        )

        for i, record in enumerate(todo, 1):
            user_input = record["question"]
            print(f"  [start] {record['method']:18s} {user_input[:40]}", flush=True)
            try:
                result = await score_record(record, golden[user_input], metrics)
            except Exception as e:
                print(f"  [fail]  {record['method']:18s} {user_input[:40]} -> {type(e).__name__}: {e}", flush=True)
                result = {
                    "question": user_input,
                    "method": record["method"],
                    "faithfulness": None,
                    "answer_relevancy": None,
                    "context_recall": None,
                    "error": f"{type(e).__name__}: {e}",
                }

            results.append(result)
            RAGAS_EVAL_PATH.write_text(json.dumps(results, indent=2))
            print(f"[{i}/{len(todo)}] {result['method']:18s} {user_input[:50]}", flush=True)

    print(f"\nWrote {len(results)} records to {RAGAS_EVAL_PATH}")
    write_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
