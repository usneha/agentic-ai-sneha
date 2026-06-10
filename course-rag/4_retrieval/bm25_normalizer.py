"""Text normalization for BM25 lexical matching.

Lowercases and strips hyphens so spelling variants like "BM25"/"bm25" and
"reranking"/"Re-ranking"/"RERANKING" tokenize to the same term.
"""


def normalize_for_bm25(text: str) -> str:
    return text.lower().replace("-", "")
