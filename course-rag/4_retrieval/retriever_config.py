"""
Retriever configuration: semantic (Chroma), BM25, and hybrid search.

Hybrid search runs both retrievers independently, then merges results via
Reciprocal Rank Fusion (RRF). Each result is tagged with its origin:
  "semantic"  — found only by vector similarity
  "bm25"      — found only by keyword match
  "both"      — found by both (strongest signal)
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Must be set before chromadb is imported
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

sys.path.insert(0, str(Path(__file__).parent.parent / "3_embeddings"))

from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from rank_bm25 import BM25Okapi

from bm25_normalizer import normalize_for_bm25
from embedder_config import get_embeddings

VECTOR_STORE_DIR = Path(__file__).parent.parent / "vector_store"
CHUNKS_PATH = Path(__file__).parent.parent / "output" / "chunks.json"
BM25_CHUNKS_PATH = Path(__file__).parent.parent / "output" / "chunks_bm25.json"
COLLECTION_NAME = "course_rag"
RRF_K = 60  # standard RRF constant


def _bm25_preprocess_func(text: str) -> List[str]:
    return normalize_for_bm25(text).split()


def get_vector_store() -> Chroma:
    return Chroma(
        persist_directory=str(VECTOR_STORE_DIR),
        embedding_function=get_embeddings(),
        collection_name=COLLECTION_NAME,
    )


def get_retriever(k: int = 5) -> VectorStoreRetriever:
    return get_vector_store().as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )


def _load_chunks() -> List[Document]:
    with open(CHUNKS_PATH) as f:
        raw = json.load(f)
    return [Document(page_content=c["content"], metadata=c["metadata"]) for c in raw]


def _load_bm25_chunks() -> List[Document]:
    """Same chunks as _load_chunks(), with metadata.normalized_text added for BM25 indexing."""
    with open(BM25_CHUNKS_PATH) as f:
        raw = json.load(f)
    return [Document(page_content=c["content"], metadata=c["metadata"]) for c in raw]


def get_bm25_retriever(k: int = 5) -> BM25Retriever:
    docs = _load_bm25_chunks()
    corpus = [_bm25_preprocess_func(doc.metadata["normalized_text"]) for doc in docs]
    return BM25Retriever(
        vectorizer=BM25Okapi(corpus),
        docs=docs,
        preprocess_func=_bm25_preprocess_func,
        k=k,
    )


def get_bm25_results_with_scores(query: str, k: int = 5) -> List[Tuple[Document, float]]:
    """Returns up to k (doc, bm25_score) pairs, sorted by score descending."""
    retriever = get_bm25_retriever()
    scores = retriever.vectorizer.get_scores(retriever.preprocess_func(query))
    scored = sorted(zip(retriever.docs, scores), key=lambda x: x[1], reverse=True)
    return [(doc, float(score)) for doc, score in scored[:k]]


def hybrid_search(
    query: str, k: int = 5
) -> List[Tuple[Document, str, float, Optional[float]]]:
    """
    Returns up to k results as (doc, origin, rrf_score, sem_score).
    origin is "semantic", "bm25", or "both". Higher rrf_score = better match.
    sem_score is the L2 distance from Chroma (lower = more similar); None for bm25-only results.
    """
    bm25_docs = get_bm25_retriever(k=k).invoke(query)
    sem_results = get_vector_store().similarity_search_with_score(query, k=k * 4)

    bm25_ranks = {doc.page_content.strip(): rank for rank, doc in enumerate(bm25_docs)}
    # top-k semantic results contribute to RRF; extended results only provide distance scores
    sem_data = {
        doc.page_content.strip(): (rank, score)
        for rank, (doc, score) in enumerate(sem_results)
    }
    sem_top_k = set(
        doc.page_content.strip() for doc, _ in sem_results[:k]
    )

    all_docs: dict[str, Document] = {}
    for doc in bm25_docs:
        all_docs[doc.page_content.strip()] = doc
    for doc, _ in sem_results:
        all_docs[doc.page_content.strip()] = doc

    results = []
    for key, doc in all_docs.items():
        in_bm25 = key in bm25_ranks
        in_sem_top = key in sem_top_k
        in_sem_any = key in sem_data
        rrf = 0.0
        if in_bm25:
            rrf += 1.0 / (bm25_ranks[key] + RRF_K)
        if in_sem_top:
            rrf += 1.0 / (sem_data[key][0] + RRF_K)

        origin = "both" if (in_bm25 and in_sem_top) else ("bm25" if in_bm25 else "semantic")
        sem_score = sem_data[key][1] if in_sem_any else None

        results.append((doc, origin, rrf, sem_score))

    results.sort(key=lambda x: x[2], reverse=True)
    return results[:k]
