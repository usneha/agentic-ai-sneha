"""
Retrieval smoke test — verifies the vector store returns coherent results.

Run from the repo root:
    uv run python 4_retrieval/run_retrieval.py

For each query, prints the top-k chunks with source and a content preview.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from retriever_config import get_retriever, hybrid_search

SAMPLE_QUERIES = [
    "How does an AI agent decide what actions to take?",
    "How does a transformer understand relationships between words?",
    "How do prompts influence model behavior?",
    "What are good ways to judge whether an LLM output is correct?",
    "What components do agentic AI systems need?",
]

# Edge cases for BM25 + semantic hybrid: each targets a scenario where the
# two retrievers are expected to behave differently.
HYBRID_EDGE_CASES = [
    ("What is BM25?", "exact acronym lookup"),
    ("What does the course say about Pinecone?", "specific tool/product name"),
    ("What does Aishwarya Srinivasan say about embeddings?", "instructor name lookup"),
    ("vector database", "short keyword query"),
    ("How can you tell if a chatbot's answer is good or bad?", "conceptual paraphrase, no shared vocabulary"),
]

K = 5


def _format_source(meta: dict) -> str:
    parts = [meta.get("source_name", "unknown")]
    if "page" in meta:
        parts.append(f"p.{meta['page']}")
    if "speaker" in meta:
        parts.append(meta["speaker"])
    parts.append(meta.get("source_type", ""))
    return "  ·  ".join(p for p in parts if p)


def _preview(text: str, length: int = 280) -> str:
    text = text.lstrip(". \n")
    text = " ".join(text.split())
    return text[:length] + ("..." if len(text) > length else "")


def run_smoke_test():
    print("🔍 Loading retriever...")
    retriever = get_retriever(k=K)
    print(f"   top-k = {K}\n")

    for qi, query in enumerate(SAMPLE_QUERIES, 1):
        print(f"{'═' * 60}")
        print(f"Q{qi}: {query}\n")
        docs = retriever.invoke(query)
        for i, doc in enumerate(docs, 1):
            print(f"  {i}.  {_format_source(doc.metadata)}")
            print(f"      {_preview(doc.page_content)}")
            print()
        print()


def run_hybrid_edge_cases():
    print(f"\n{'═' * 60}")
    print("Hybrid (BM25 + semantic) edge cases")
    print(f"top-k = {K}\n")

    for qi, (query, label) in enumerate(HYBRID_EDGE_CASES, 1):
        print(f"{'═' * 60}")
        print(f"E{qi} [{label}]: {query}\n")
        for i, (doc, origin, rrf, sem_score) in enumerate(hybrid_search(query, k=K), 1):
            print(f"  {i}.  [{origin}]  {_format_source(doc.metadata)}")
            print(f"      {_preview(doc.page_content)}")
            print()
        print()


if __name__ == "__main__":
    run_smoke_test()
    run_hybrid_edge_cases()
