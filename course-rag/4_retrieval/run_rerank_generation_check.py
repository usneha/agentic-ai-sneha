"""
Focused generation check for Q4: does the cross-encoder reranked top-5
context produce a materially different gpt-4o-mini answer than the existing
hybrid (no-reranking) baseline in output/rag_eval.json?

Run from the repo root (requires OPENAI_API_KEY in .env):
    uv run python 4_retrieval/run_rerank_generation_check.py
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from langchain_openai import ChatOpenAI

from reranker_config import hybrid_search_reranked
from run_rag_eval import GEN_MODEL, SYSTEM_PROMPT, _build_context

QUERY = "What are good ways to judge whether an LLM output is correct?"
RAG_EVAL_PATH = Path(__file__).parent.parent / "output" / "rag_eval.json"


def main():
    rag_eval = json.loads(RAG_EVAL_PATH.read_text())
    baseline = next(r for r in rag_eval if r["question"] == QUERY and r["method"] == "hybrid")

    reranked = hybrid_search_reranked(QUERY, k=5, candidate_k=20)
    docs = [doc for doc, _origin, _score, _sem in reranked]
    context = _build_context(docs)

    llm = ChatOpenAI(model=GEN_MODEL, temperature=0)
    response = llm.invoke(
        [
            ("system", SYSTEM_PROMPT),
            ("user", f"Context:\n\n{context}\n\nQuestion: {QUERY}"),
        ]
    )

    print("=" * 60)
    print("BASELINE (hybrid, no reranking)")
    print("=" * 60)
    print(baseline["answer"])
    print()
    print("=" * 60)
    print("RERANKED (cross-encoder top-5, candidate_k=20)")
    print("=" * 60)
    print(response.content)


if __name__ == "__main__":
    main()
