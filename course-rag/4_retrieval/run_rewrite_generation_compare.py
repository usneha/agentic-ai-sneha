"""
Generation comparison for the two rewrite-prompt variants tried for Q1/Q3/Q5,
where retrieval scores diverged from the baseline (no rewriting).

For each of Q1 ("How does an AI agent decide what actions to take?"),
Q3 ("How do prompts influence model behavior?"), and
Q5 ("What components do agentic AI systems need?"):
  - prints the rewrite from each prompt variant
  - retrieves via hybrid_search_reranked(rewritten, k=5, candidate_k=20)
  - generates an answer to the *original* question with that context
  - prints both next to the existing hybrid baseline answer from
    output/rag_eval.json

AGGRESSIVE_PROMPT is the first rewrite prompt tried (course-topic-aware,
keyword-dense). CONSERVATIVE_PROMPT is query_rewriter.REWRITE_SYSTEM_PROMPT
(current).

Run from the repo root (requires OPENAI_API_KEY in .env):
    uv run python 4_retrieval/run_rewrite_generation_compare.py
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

from query_rewriter import REWRITE_MODEL, REWRITE_SYSTEM_PROMPT as CONSERVATIVE_PROMPT
from reranker_config import hybrid_search_reranked
from run_rag_eval import GEN_MODEL, SYSTEM_PROMPT, _build_context

AGGRESSIVE_PROMPT = (
    "You rewrite questions into search queries for a retrieval system over "
    "course material on Agentic AI, RAG, embeddings, retrieval, and LLM "
    "evaluation. Rewrite the user's question as a concise, keyword-dense "
    "search query using the precise technical terminology (metric names, "
    "framework names, concepts) that the course material is likely to use. "
    "Preserve the original intent and keep any proper nouns (tool names, "
    "person names, acronyms) exactly as written. "
    "Output only the rewritten query, with no explanation or punctuation."
)

RAG_EVAL_PATH = Path(__file__).parent.parent / "output" / "rag_eval.json"

QUESTIONS = [
    "How does an AI agent decide what actions to take?",
    "How do prompts influence model behavior?",
    "What components do agentic AI systems need?",
]


def _rewrite(question: str, system_prompt: str, llm: ChatOpenAI) -> str:
    response = llm.invoke([("system", system_prompt), ("user", question)])
    return response.content.strip()


def _generate(question: str, rewritten: str, llm: ChatOpenAI) -> tuple[str, list]:
    reranked = hybrid_search_reranked(rewritten, k=5, candidate_k=20)
    docs = [doc for doc, _origin, _score, _sem in reranked]
    context = _build_context(docs)
    response = llm.invoke(
        [
            ("system", SYSTEM_PROMPT),
            ("user", f"Context:\n\n{context}\n\nQuestion: {question}"),
        ]
    )
    return response.content, reranked


def main():
    rag_eval = json.loads(RAG_EVAL_PATH.read_text())
    rewrite_llm = ChatOpenAI(model=REWRITE_MODEL, temperature=0)
    gen_llm = ChatOpenAI(model=GEN_MODEL, temperature=0)

    for question in QUESTIONS:
        baseline = next(r for r in rag_eval if r["question"] == question and r["method"] == "hybrid")

        aggressive_rewrite = _rewrite(question, AGGRESSIVE_PROMPT, rewrite_llm)
        conservative_rewrite = _rewrite(question, CONSERVATIVE_PROMPT, rewrite_llm)

        aggressive_answer, _ = _generate(question, aggressive_rewrite, gen_llm)
        conservative_answer, _ = _generate(question, conservative_rewrite, gen_llm)

        print("=" * 60)
        print(f"Q: {question}")
        print(f"  aggressive rewrite:   {aggressive_rewrite}")
        print(f"  conservative rewrite: {conservative_rewrite}")
        print("=" * 60)
        print("BASELINE (hybrid, no rewriting)")
        print(baseline["answer"])
        print()
        print("AGGRESSIVE PROMPT REWRITE + RERANKED")
        print(aggressive_answer)
        print()
        print("CONSERVATIVE PROMPT REWRITE + RERANKED")
        print(conservative_answer)
        print()


if __name__ == "__main__":
    main()
