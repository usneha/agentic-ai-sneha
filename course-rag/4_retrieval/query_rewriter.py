"""
Query rewriting for retrieval: reformulates a conversational question into a
concise, keyword-dense search query using the technical terminology the
course material is likely to use (metric names, framework names, etc.),
while preserving intent and any proper nouns.

The rewritten query is intended for retrieval only — the original question
should still be passed to the generation LLM so citations and phrasing match
what the user actually asked.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from langchain_openai import ChatOpenAI

REWRITE_MODEL = "gpt-4o-mini"

REWRITE_SYSTEM_PROMPT = (
    "You rewrite questions into search queries for a retrieval system over "
    "course material on Agentic AI, RAG, embeddings, retrieval, and LLM "
    "evaluation. Rewrite the user's question as a concise, keyword-dense "
    "search query using the precise technical terminology (metric names, "
    "framework names, concepts) that the course material is likely to use. "
    "Preserve the original intent and keep any proper nouns (tool names, "
    "person names, acronyms) exactly as written. "
    "Output only the rewritten query, with no explanation or punctuation."
)

_llm = None


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(model=REWRITE_MODEL, temperature=0)
    return _llm


def rewrite_query(question: str) -> str:
    """Reformulate a conversational question into a retrieval-friendly search query."""
    response = _get_llm().invoke(
        [
            ("system", REWRITE_SYSTEM_PROMPT),
            ("user", question),
        ]
    )
    return response.content.strip()
