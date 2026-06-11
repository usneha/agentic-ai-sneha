"""
Force-include check for the Q4 retrieval gap.

Takes the existing hybrid top-5 context for Q4 and appends chunk #476
("Building a Golden Dataset for Evaluation" — the chunk that explicitly names
precision/NDCG/recall/MRR/faithfulness, which never surfaces in semantic or
BM25 top-20). Compares the gpt-4o-mini answer with that chunk forced in
against the existing hybrid baseline in output/rag_eval.json, to confirm
whether the hedge ("cannot provide a definitive answer") is purely a
retrieval-coverage issue.

Run from the repo root (requires OPENAI_API_KEY in .env):
    uv run python 4_retrieval/run_force_include_check.py
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from retriever_config import hybrid_search
from run_rag_eval import GEN_MODEL, SYSTEM_PROMPT, _build_context

QUERY = "What are good ways to judge whether an LLM output is correct?"
RAG_EVAL_PATH = Path(__file__).parent.parent / "output" / "rag_eval.json"
CHUNKS_PATH = Path(__file__).parent.parent / "output" / "chunks.json"
TARGET_CHUNK_INDEX = 476


def main():
    rag_eval = json.loads(RAG_EVAL_PATH.read_text())
    baseline = next(r for r in rag_eval if r["question"] == QUERY and r["method"] == "hybrid")

    chunks = json.loads(CHUNKS_PATH.read_text())
    target = chunks[TARGET_CHUNK_INDEX]
    target_doc = Document(page_content=target["content"], metadata=target["metadata"])

    hybrid_results = hybrid_search(QUERY, k=5)
    hybrid_docs = [doc for doc, _origin, _rrf, _sem in hybrid_results]

    forced_docs = hybrid_docs + [target_doc]
    context = _build_context(forced_docs)

    llm = ChatOpenAI(model=GEN_MODEL, temperature=0)
    response = llm.invoke(
        [
            ("system", SYSTEM_PROMPT),
            ("user", f"Context:\n\n{context}\n\nQuestion: {QUERY}"),
        ]
    )

    print("=" * 60)
    print("BASELINE (hybrid top-5, no forced chunk)")
    print("=" * 60)
    print(baseline["answer"])
    print()
    print("=" * 60)
    print("FORCED (hybrid top-5 + chunk #476 'Building a Golden Dataset for Evaluation')")
    print("=" * 60)
    print(response.content)


if __name__ == "__main__":
    main()
