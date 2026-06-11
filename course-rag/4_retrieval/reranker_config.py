"""
Cross-encoder re-ranking on top of semantic + BM25 candidates.

hybrid_search_reranked() builds its candidate pool as the deduped union of
semantic top-candidate_k and BM25 top-candidate_k results (rather than an
RRF-merged top-candidate_k), then re-scores every candidate with a
cross-encoder and returns the top-k by cross-encoder score. The union avoids
RRF's cutoff dropping a chunk that ranks well in only one retriever (e.g.
BM25 rank ~17) before the cross-encoder ever sees it.
"""

import sys
from pathlib import Path
from typing import List, Optional, Tuple

from langchain_core.documents import Document
from sentence_transformers import CrossEncoder

sys.path.insert(0, str(Path(__file__).parent))

from query_rewriter import rewrite_query
from retriever_config import get_bm25_results_with_scores, get_vector_store

CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_cross_encoder: Optional[CrossEncoder] = None


def get_cross_encoder() -> CrossEncoder:
    """Lazily load and cache the cross-encoder model (downloads on first use)."""
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL)
    return _cross_encoder


def get_candidate_pool(
    query: str, candidate_k: int = 20
) -> List[Tuple[Document, str, Optional[float]]]:
    """
    Returns the deduped union of semantic top-candidate_k and BM25
    top-candidate_k results as (doc, origin, sem_score) tuples.
    origin is "semantic", "bm25", or "both"; sem_score is the L2 distance
    from Chroma (lower = more similar), or None for BM25-only candidates.
    """
    sem_results = get_vector_store().similarity_search_with_score(query, k=candidate_k)
    bm25_results = get_bm25_results_with_scores(query, k=candidate_k)

    sem_scores = {doc.page_content.strip(): score for doc, score in sem_results}
    bm25_keys = {doc.page_content.strip() for doc, _score in bm25_results}

    all_docs: dict[str, Document] = {}
    for doc, _score in sem_results:
        all_docs[doc.page_content.strip()] = doc
    for doc, _score in bm25_results:
        all_docs[doc.page_content.strip()] = doc

    candidates = []
    for key, doc in all_docs.items():
        in_sem = key in sem_scores
        in_bm25 = key in bm25_keys
        origin = "both" if (in_sem and in_bm25) else ("semantic" if in_sem else "bm25")
        candidates.append((doc, origin, sem_scores.get(key)))
    return candidates


def hybrid_search_reranked(
    query: str, k: int = 5, candidate_k: int = 20
) -> List[Tuple[Document, str, float, Optional[float]]]:
    """
    Builds the candidate pool via get_candidate_pool(), re-scores every
    candidate with a cross-encoder, and returns the top-k re-sorted by
    cross-encoder score.

    Returns (doc, origin, rerank_score, sem_score). origin is "semantic",
    "bm25", or "both"; rerank_score is the cross-encoder score (higher = more
    relevant); sem_score is the L2 distance from Chroma, or None for
    BM25-only candidates.
    """
    candidates = get_candidate_pool(query, candidate_k=candidate_k)
    if not candidates:
        return []

    pairs = [(query, doc.page_content) for doc, _origin, _sem in candidates]
    scores = get_cross_encoder().predict(pairs)

    reranked = [
        (doc, origin, float(score), sem_score)
        for (doc, origin, sem_score), score in zip(candidates, scores)
    ]
    reranked.sort(key=lambda x: x[2], reverse=True)
    return reranked[:k]


def hybrid_search_rewritten_reranked(
    query: str, k: int = 5, candidate_k: int = 20
) -> List[Tuple[Document, str, float, Optional[float]]]:
    """
    Rewrites the query into a retrieval-friendly form via rewrite_query(),
    then runs hybrid_search_reranked() on the rewritten query. Returns the
    same (doc, origin, rerank_score, sem_score) shape as
    hybrid_search_reranked().
    """
    rewritten = rewrite_query(query)
    return hybrid_search_reranked(rewritten, k=k, candidate_k=candidate_k)
