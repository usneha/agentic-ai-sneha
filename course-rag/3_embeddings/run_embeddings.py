"""
Run from the repo root:
    uv run python 3_embeddings/run_embeddings.py

Reads:  output/chunks.json
Writes: vector_store/  (Chroma persistent store, collection: course_rag)

To switch to OpenAI embeddings:
    EMBEDDING_PROVIDER=openai uv run python 3_embeddings/run_embeddings.py
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path

# Must be set before chromadb is imported — protobuf>=4 breaks chromadb's opentelemetry dep
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

sys.path.insert(0, str(Path(__file__).parent))

from langchain_chroma import Chroma
from langchain_core.documents import Document

from embedder_config import PROVIDER, get_embeddings

CHUNKS_PATH = Path(__file__).parent.parent / "output" / "chunks.json"
VECTOR_STORE_DIR = Path(__file__).parent.parent / "vector_store"
COLLECTION_NAME = "course_rag"


def load_chunks(path: Path) -> list[Document]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Document(page_content=d["content"], metadata=d["metadata"]) for d in raw]


def run_embeddings():
    print(f"📂 Loading chunks from {CHUNKS_PATH}...")
    chunks = load_chunks(CHUNKS_PATH)
    print(f"   → {len(chunks)} chunks loaded")

    print(f"\n🔧 Embedding provider : {PROVIDER}")
    if PROVIDER == "huggingface":
        print(f"   Model              : all-MiniLM-L6-v2 (local)")
    else:
        print(f"   Model              : text-embedding-3-small (OpenAI)")

    embeddings = get_embeddings()

    if VECTOR_STORE_DIR.exists():
        print(f"\n⚠️  Removing existing vector store...")
        shutil.rmtree(VECTOR_STORE_DIR)

    print(f"\n🔢 Embedding {len(chunks)} chunks...")
    start = time.time()

    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(VECTOR_STORE_DIR),
        collection_name=COLLECTION_NAME,
    )

    elapsed = time.time() - start
    count = vector_store._collection.count()

    print(f"\n✅ Done in {elapsed:.1f}s")
    print(f"   vectors    : {count:,}")
    print(f"   collection : {COLLECTION_NAME}")
    print(f"   location   : {VECTOR_STORE_DIR}")


if __name__ == "__main__":
    run_embeddings()
