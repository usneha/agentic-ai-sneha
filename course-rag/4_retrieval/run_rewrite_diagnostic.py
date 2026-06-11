"""
Query-rewriting diagnostic.

a) For the 5 SAMPLE_QUERIES, prints the rewrite_query() output alongside the
   original, and compares hybrid_search_reranked() top-5 with vs. without
   rewriting — flags whether the top-5 set changed, to surface regressions
   on queries that already retrieve well.

b) Re-confirms the Q4 fix end-to-end using the real rewrite_query() output:
   retrieves via hybrid_search_rewritten_reranked(), generates an answer to
   the original Q4 question with that context, and prints it next to the
   existing hybrid baseline answer from output/rag_eval.json.

Run from the repo root (requires OPENAI_API_KEY in .env):
    uv run python 4_retrieval/run_rewrite_diagnostic.py
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

from query_rewriter import rewrite_query
from reranker_config import hybrid_search_reranked, hybrid_search_rewritten_reranked
from run_rag_eval import GEN_MODEL, SYSTEM_PROMPT, _build_context
from run_retrieval import SAMPLE_QUERIES

RAG_EVAL_PATH = Path(__file__).parent.parent / "output" / "rag_eval.json"
Q4 = "What are good ways to judge whether an LLM output is correct?"


def _format_source(meta: dict) -> str:
    parts = [meta.get("source_name", "unknown")]
    if "page" in meta:
        parts.append(f"p.{meta['page']}")
    if "chapter_title" in meta:
        parts.append(meta["chapter_title"])
    return "  ·  ".join(p for p in parts if p)


def _preview(text: str, length: int = 150) -> str:
    text = text.lstrip(". \n")
    text = " ".join(text.split())
    return text[:length] + ("..." if len(text) > length else "")


def _doc_key(doc) -> str:
    return doc.page_content.strip()


def validate_sample_queries():
    print(f"{'═' * 60}")
    print("Part A: rewrite + rerank vs. rerank-only on SAMPLE_QUERIES\n")

    for qi, query in enumerate(SAMPLE_QUERIES, 1):
        rewritten = rewrite_query(query)
        print(f"Q{qi}: {query}")
        print(f"  rewritten: {rewritten}")

        original_results = hybrid_search_reranked(query, k=5, candidate_k=20)
        rewritten_results = hybrid_search_reranked(rewritten, k=5, candidate_k=20)

        original_keys = {_doc_key(doc) for doc, _o, _s, _sem in original_results}
        rewritten_keys = {_doc_key(doc) for doc, _o, _s, _sem in rewritten_results}
        changed = original_keys != rewritten_keys

        print(f"  top-5 changed: {changed}")
        print("  reranked (original query):")
        for i, (doc, origin, score, _sem) in enumerate(original_results, 1):
            print(f"    {i}. [{origin:8s}] score={score:.4f}  {_format_source(doc.metadata)}")
            print(f"       {_preview(doc.page_content)}")
        print("  reranked (rewritten query):")
        for i, (doc, origin, score, _sem) in enumerate(rewritten_results, 1):
            flag = "  <-- new" if _doc_key(doc) not in original_keys else ""
            print(f"    {i}. [{origin:8s}] score={score:.4f}  {_format_source(doc.metadata)}{flag}")
            print(f"       {_preview(doc.page_content)}")
        print()


def confirm_q4_end_to_end():
    print(f"{'═' * 60}")
    print("Part B: Q4 end-to-end with real rewrite_query() output\n")

    rewritten = rewrite_query(Q4)
    print(f"Q4: {Q4}")
    print(f"rewritten: {rewritten}\n")

    rag_eval = json.loads(RAG_EVAL_PATH.read_text())
    baseline = next(r for r in rag_eval if r["question"] == Q4 and r["method"] == "hybrid")

    reranked = hybrid_search_rewritten_reranked(Q4, k=5, candidate_k=20)
    docs = [doc for doc, _origin, _score, _sem in reranked]
    context = _build_context(docs)

    llm = ChatOpenAI(model=GEN_MODEL, temperature=0)
    response = llm.invoke(
        [
            ("system", SYSTEM_PROMPT),
            ("user", f"Context:\n\n{context}\n\nQuestion: {Q4}"),
        ]
    )

    print("retrieved (rewritten + reranked):")
    for i, (doc, origin, score, _sem) in enumerate(reranked, 1):
        print(f"  {i}. [{origin:8s}] score={score:.4f}  {_format_source(doc.metadata)}")
        print(f"     {_preview(doc.page_content)}")
    print()

    print("=" * 60)
    print("BASELINE (hybrid, no rewriting/reranking)")
    print("=" * 60)
    print(baseline["answer"])
    print()
    print("=" * 60)
    print("REWRITTEN + RERANKED")
    print("=" * 60)
    print(response.content)


if __name__ == "__main__":
    validate_sample_queries()
    confirm_q4_end_to_end()
