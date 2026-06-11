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


CONTEXTUALIZE_SYSTEM_PROMPT = (
    "Given the conversation so far and a new user message, rewrite the new "
    "message as a standalone question that includes any context (topics, "
    "entities, acronyms) needed to understand it without the conversation. "
    "If it is already standalone, return it unchanged. "
    "Output only the rewritten question, with no explanation."
)


def contextualize_query(history: list[dict], question: str) -> str:
    """Resolve pronouns/implicit references in a follow-up question using
    prior conversation turns, producing a standalone question for retrieval."""
    if not history:
        return question

    messages = [("system", CONTEXTUALIZE_SYSTEM_PROMPT)]
    messages += [(m["role"], m["content"]) for m in history]
    messages.append(("user", question))

    response = _get_llm().invoke(messages)
    return response.content.strip()
