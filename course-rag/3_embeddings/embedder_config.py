"""
Embedding model factory.

Set EMBEDDING_PROVIDER in .env or environment:
  huggingface  (default) — local, no API key needed; uses all-MiniLM-L6-v2
  openai                 — requires OPENAI_API_KEY; uses text-embedding-3-small
"""

import os

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("EMBEDDING_PROVIDER", "huggingface").lower()
OPENAI_MODEL = "text-embedding-3-small"
HF_MODEL = "all-MiniLM-L6-v2"


def get_embeddings():
    if PROVIDER == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=OPENAI_MODEL)

    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name=HF_MODEL)
