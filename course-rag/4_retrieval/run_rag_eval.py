"""
RAG generation evaluation: for each question, retrieves top-k chunks via
semantic, BM25, and hybrid search, then asks an LLM to answer using only
that context. Generated answers are written alongside the retrieved chunks
so retrieval and generation quality can be reviewed side by side.

Run from the repo root (requires OPENAI_API_KEY in .env):
    uv run python 4_retrieval/run_rag_eval.py

Writes results to output/rag_eval.json
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

from retriever_config import get_bm25_results_with_scores, get_vector_store, hybrid_search
from run_retrieval import HYBRID_EDGE_CASES, SAMPLE_QUERIES

QUESTIONS = SAMPLE_QUERIES + [query for query, _label in HYBRID_EDGE_CASES]
K = 5
GEN_MODEL = "gpt-4o-mini"
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "rag_eval.json"

SYSTEM_PROMPT = (
    "You are a helpful assistant answering questions about an Agentic AI "
    "course based only on the provided context. If the context does not "
    "contain enough information to answer, say so explicitly rather than "
    "guessing.\n\n"
    "Each context block is prefixed with its source, e.g. "
    "[Source: session1-week2-lecture-raw-transcript · Choosing an Embedding Model]. "
    "After each claim or sentence drawn from the context, cite the source it came "
    "from inline using that same format, e.g. (Source: ...). If a sentence draws "
    "on multiple sources, cite all of them."
)


def _source_label(meta: dict) -> str:
    parts = [meta.get("source_name", "unknown")]
    if "page" in meta:
        parts.append(f"p.{meta['page']}")
    if "chapter_title" in meta:
        parts.append(meta["chapter_title"])
    return "  ·  ".join(parts)


def _build_context(docs) -> str:
    blocks = []
    for doc in docs:
        blocks.append(f"[Source: {_source_label(doc.metadata)}]\n{doc.page_content}")
    return "\n\n---\n\n".join(blocks)


def _docs_for(method: str, question: str):
    if method == "semantic":
        return get_vector_store().similarity_search(question, k=K)
    if method == "bm25":
        return [doc for doc, _score in get_bm25_results_with_scores(question, k=K)]
    if method == "hybrid":
        return [doc for doc, _origin, _rrf, _sem in hybrid_search(question, k=K)]
    raise ValueError(method)


def _chunk_record(doc) -> dict:
    meta = doc.metadata
    record = {
        "source_name": meta.get("source_name"),
        "source_type": meta.get("source_type"),
        "chunk_text": doc.page_content,
    }
    if meta.get("source_type") == "pdf":
        record["page"] = meta.get("page")
    elif meta.get("source_type") == "transcript_chapter":
        record["chapter_title"] = meta.get("chapter_title")
        record["timestamp_start"] = meta.get("timestamp_start")
    return record


def run_rag_eval():
    llm = ChatOpenAI(model=GEN_MODEL, temperature=0)
    results = []

    for question in QUESTIONS:
        for method in ("semantic", "bm25", "hybrid"):
            docs = _docs_for(method, question)
            context = _build_context(docs)
            response = llm.invoke(
                [
                    ("system", SYSTEM_PROMPT),
                    ("user", f"Context:\n\n{context}\n\nQuestion: {question}"),
                ]
            )
            results.append(
                {
                    "question": question,
                    "method": method,
                    "answer": response.content,
                    "chunks": [_chunk_record(doc) for doc in docs],
                }
            )
            print(f"[{method}] {question[:60]}")

    OUTPUT_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {len(results)} records to {OUTPUT_PATH}")


if __name__ == "__main__":
    run_rag_eval()
