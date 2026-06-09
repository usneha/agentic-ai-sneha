"""
Loads the Chroma vector store and returns a retriever.

Reuses embedder_config from 3_embeddings — the same model must be used
for both indexing and querying.
"""

import os
import sys
from pathlib import Path

# Must be set before chromadb is imported
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

sys.path.insert(0, str(Path(__file__).parent.parent / "3_embeddings"))

from langchain_chroma import Chroma
from langchain_core.vectorstores import VectorStoreRetriever

from embedder_config import get_embeddings

VECTOR_STORE_DIR = Path(__file__).parent.parent / "vector_store"
COLLECTION_NAME = "course_rag"


def get_retriever(k: int = 5) -> VectorStoreRetriever:
    vector_store = Chroma(
        persist_directory=str(VECTOR_STORE_DIR),
        embedding_function=get_embeddings(),
        collection_name=COLLECTION_NAME,
    )
    return vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )
