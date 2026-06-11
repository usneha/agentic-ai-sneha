"""
Retrieval evaluation: runs each question through semantic-only, BM25-only,
and hybrid (RRF) retrieval, storing the chunk text, source metadata, method,
and score for each result so methods can be compared offline.

Run from the repo root:
    uv run python 4_retrieval/run_eval.py

Writes results to output/retrieval_eval.json
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reranker_config import hybrid_search_rewritten_reranked
from retriever_config import get_bm25_results_with_scores, get_vector_store, hybrid_search
from run_retrieval import HYBRID_EDGE_CASES, SAMPLE_QUERIES

QUESTIONS = SAMPLE_QUERIES + [query for query, _label in HYBRID_EDGE_CASES]
K = 5
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "retrieval_eval.json"

# Opt-in: also run a rewrite_query() + cross-encoder-reranked method.
# Default (unset) keeps output identical to the existing 3-method eval.
ENABLE_REWRITE_RERANK = os.getenv("ENABLE_REWRITE_RERANK", "false").lower() == "true"


def _record(question, method, rank, score, doc, origin=None):
    meta = doc.metadata
    record = {
        "question": question,
        "method": method,
        "rank": rank,
        "score": score,
        "chunk_text": doc.page_content,
        "source_name": meta.get("source_name"),
        "source_type": meta.get("source_type"),
    }
    if origin is not None:
        record["origin"] = origin
    if meta.get("source_type") == "pdf":
        record["page"] = meta.get("page")
    elif meta.get("source_type") == "transcript_chapter":
        record["chapter_title"] = meta.get("chapter_title")
        record["timestamp_start"] = meta.get("timestamp_start")
    return record


def run_eval():
    vector_store = get_vector_store()
    results = []

    for question in QUESTIONS:
        for rank, (doc, score) in enumerate(
            vector_store.similarity_search_with_score(question, k=K), 1
        ):
            results.append(_record(question, "semantic", rank, float(score), doc))

        for rank, (doc, score) in enumerate(
            get_bm25_results_with_scores(question, k=K), 1
        ):
            results.append(_record(question, "bm25", rank, score, doc))

        for rank, (doc, origin, rrf, _sem_score) in enumerate(
            hybrid_search(question, k=K), 1
        ):
            results.append(_record(question, "hybrid", rank, rrf, doc, origin=origin))

        if ENABLE_REWRITE_RERANK:
            for rank, (doc, origin, score, _sem_score) in enumerate(
                hybrid_search_rewritten_reranked(question, k=K), 1
            ):
                results.append(_record(question, "rewritten_reranked", rank, score, doc, origin=origin))

    n_methods = 4 if ENABLE_REWRITE_RERANK else 3
    OUTPUT_PATH.write_text(json.dumps(results, indent=2))
    print(
        f"Wrote {len(results)} records "
        f"({len(QUESTIONS)} questions x {n_methods} methods x k={K}) to {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    run_eval()
