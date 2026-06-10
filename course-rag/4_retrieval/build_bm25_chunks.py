"""
Builds output/chunks_bm25.json from output/chunks.json (left unchanged).

Each record keeps the original "content" and "metadata", with an added
metadata.normalized_text field (lowercased, hyphens stripped) used for
BM25 indexing/scoring while page_content stays the original text.

Run from the repo root:
    uv run python 4_retrieval/build_bm25_chunks.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bm25_normalizer import normalize_for_bm25

CHUNKS_PATH = Path(__file__).parent.parent / "output" / "chunks.json"
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "chunks_bm25.json"


def build_bm25_chunks():
    chunks = json.loads(CHUNKS_PATH.read_text())

    records = []
    for chunk in chunks:
        records.append(
            {
                "content": chunk["content"],
                "metadata": {
                    **chunk["metadata"],
                    "normalized_text": normalize_for_bm25(chunk["content"]),
                },
            }
        )

    OUTPUT_PATH.write_text(json.dumps(records, indent=2))
    print(f"Wrote {len(records)} records to {OUTPUT_PATH}")


if __name__ == "__main__":
    build_bm25_chunks()
