"""
RAG generator: query-rewritten, cross-encoder-reranked hybrid retrieval
(BM25 + semantic) then gpt-4o-mini.

Usage:
    from generator import generate
    answer, results = generate("How do agents decide what to do?")
    # results: List[Tuple[Document, origin_str, rerank_score, sem_score]]
"""

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Must be set before chromadb is imported
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent / "4_retrieval"))
from reranker_config import hybrid_search_rewritten_reranked

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """\
You are a teaching assistant for the "Mastering Agentic AI" course.
Answer the student's question using only the course material excerpts provided below.
Cite sources inline using the label [Source N] that appears before each excerpt.
If the excerpts only partially answer the question, explicitly say that the course material only partially covers the topic.

If the excerpts do not clearly contain the answer, say that the course material does not contain enough information to answer confidently.

Do not use outside knowledge.
Do not infer missing details.
Do not attribute claims to sources unless the claim is explicitly supported by the excerpts.

Be concise but complete."""


def _build_context(results: List[Tuple[Document, str, float, Optional[float]]]) -> str:
    parts = []
    for i, (doc, origin, _, _sem) in enumerate(results, 1):
        meta = doc.metadata
        label = meta.get("source_name", "unknown")
        if "page" in meta:
            label += f" p.{meta['page']}"
        if "speaker" in meta:
            label += f" — {meta['speaker']}"
        parts.append(f"[Source {i}] {label}\n{doc.page_content.strip()}")
    return "\n\n---\n\n".join(parts)


def generate(query: str, k: int = 5) -> Tuple[str, List[Tuple[Document, str, float, Optional[float]]]]:
    results = hybrid_search_rewritten_reranked(query, k=k)

    if not results:
        return "The course material does not contain enough information to answer this question.", []

    context = _build_context(results)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n\n{context}\n\nQuestion: {query}"},
    ]

    llm = ChatOpenAI(model=MODEL, temperature=0)
    response = llm.invoke(messages)
    return response.content, results
