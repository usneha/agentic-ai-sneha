"""
Re-ranking diagnostic for the Q4 retrieval gap.

For the question "What are good ways to judge whether an LLM output is
correct?", prints:
  - semantic top-20
  - BM25 top-20
  - candidate pool (semantic top-20 ∪ BM25 top-20, deduped) — what the
    reranker sees
  - cross-encoder reranked top-8, flagging the target "RAG Evaluation
    Metrics" / "Building a Golden Dataset for Evaluation" chunks if present
  - token count + estimated LLM input cost for top-5 vs top-8 context
  - re-ranking latency (model load vs. per-query inference)

Run from the repo root:
    uv run python 4_retrieval/run_rerank_diagnostic.py
"""

import sys
import time
from pathlib import Path

import tiktoken

sys.path.insert(0, str(Path(__file__).parent))

from retriever_config import get_bm25_results_with_scores, get_vector_store
from reranker_config import get_candidate_pool, get_cross_encoder, hybrid_search_reranked

QUERY = "What are good ways to judge whether an LLM output is correct?"
CANDIDATE_K = 20
RERANK_K = 8
GEN_MODEL = "gpt-4o-mini"
GPT4O_MINI_INPUT_PRICE_PER_1M = 0.15  # USD per 1M input tokens, as of mid-2025 — verify if pricing changed

TARGET_SOURCE = "session2-week2-lecture-raw-transcript"
TARGET_CHAPTERS = {"RAG Evaluation Metrics", "Building a Golden Dataset for Evaluation"}


def _format_source(meta: dict) -> str:
    parts = [meta.get("source_name", "unknown")]
    if "page" in meta:
        parts.append(f"p.{meta['page']}")
    if "chapter_title" in meta:
        parts.append(meta["chapter_title"])
    parts.append(meta.get("source_type", ""))
    return "  ·  ".join(p for p in parts if p)


def _preview(text: str, length: int = 200) -> str:
    text = text.lstrip(". \n")
    text = " ".join(text.split())
    return text[:length] + ("..." if len(text) > length else "")


def _is_target(meta: dict) -> bool:
    return meta.get("source_name") == TARGET_SOURCE and meta.get("chapter_title") in TARGET_CHAPTERS


def _build_context(docs) -> str:
    blocks = []
    for doc in docs:
        blocks.append(f"[Source: {_format_source(doc.metadata)}]\n{doc.page_content}")
    return "\n\n---\n\n".join(blocks)


def print_semantic_top20():
    print(f"{'═' * 60}")
    print(f"Semantic top-{CANDIDATE_K}\n")
    results = get_vector_store().similarity_search_with_score(QUERY, k=CANDIDATE_K)
    for i, (doc, score) in enumerate(results, 1):
        flag = "  <-- TARGET" if _is_target(doc.metadata) else ""
        print(f"  {i:2d}.  score={score:.4f}  {_format_source(doc.metadata)}{flag}")
        print(f"       {_preview(doc.page_content)}")
    print()


def print_bm25_top20():
    print(f"{'═' * 60}")
    print(f"BM25 top-{CANDIDATE_K}\n")
    results = get_bm25_results_with_scores(QUERY, k=CANDIDATE_K)
    for i, (doc, score) in enumerate(results, 1):
        flag = "  <-- TARGET" if _is_target(doc.metadata) else ""
        print(f"  {i:2d}.  score={score:.4f}  {_format_source(doc.metadata)}{flag}")
        print(f"       {_preview(doc.page_content)}")
    print()


def print_candidate_pool():
    print(f"{'═' * 60}")
    pool = get_candidate_pool(QUERY, candidate_k=CANDIDATE_K)
    print(f"Candidate pool: semantic top-{CANDIDATE_K} ∪ BM25 top-{CANDIDATE_K}, deduped -> {len(pool)} candidates\n")
    for i, (doc, origin, _sem) in enumerate(pool, 1):
        flag = "  <-- TARGET" if _is_target(doc.metadata) else ""
        print(f"  {i:2d}.  [{origin:8s}]  {_format_source(doc.metadata)}{flag}")
        print(f"       {_preview(doc.page_content)}")
    print()
    return pool


def print_reranked_top8():
    print(f"{'═' * 60}")
    print(f"Cross-encoder reranked top-{RERANK_K} (candidate_k={CANDIDATE_K})\n")
    reranked = hybrid_search_reranked(QUERY, k=RERANK_K, candidate_k=CANDIDATE_K)
    for i, (doc, origin, score, _sem) in enumerate(reranked, 1):
        flag = "  <-- TARGET" if _is_target(doc.metadata) else ""
        print(f"  {i:2d}.  [{origin:8s}]  score={score:.4f}  {_format_source(doc.metadata)}{flag}")
        print(f"       {_preview(doc.page_content)}")
    print()
    return reranked


def print_token_cost(reranked):
    print(f"{'═' * 60}")
    print("Token cost / latency for passing reranked context to the LLM\n")
    enc = tiktoken.encoding_for_model(GEN_MODEL)
    for top_n in (5, RERANK_K):
        docs = [doc for doc, _origin, _score, _sem in reranked[:top_n]]
        context = _build_context(docs)
        n_tokens = len(enc.encode(context))
        cost = n_tokens / 1_000_000 * GPT4O_MINI_INPUT_PRICE_PER_1M
        print(f"  top-{top_n}: {n_tokens:5d} tokens  ->  ${cost:.6f} input cost ({GEN_MODEL})")
    print()


def print_latency(pool):
    print(f"{'═' * 60}")
    print("Re-ranking latency\n")

    t0 = time.perf_counter()
    model = get_cross_encoder()
    t1 = time.perf_counter()
    print(f"  model load (incl. download if needed): {t1 - t0:.3f}s")

    pairs = [(QUERY, doc.page_content) for doc, _origin, _sem in pool]
    t2 = time.perf_counter()
    model.predict(pairs)
    t3 = time.perf_counter()
    print(f"  inference over {len(pairs)} candidates:     {(t3 - t2) * 1000:.1f}ms")
    print()


if __name__ == "__main__":
    print(f"Q4: {QUERY}\n")
    print_semantic_top20()
    print_bm25_top20()
    pool = print_candidate_pool()
    print_latency(pool)
    reranked = print_reranked_top8()
    print_token_cost(reranked)
