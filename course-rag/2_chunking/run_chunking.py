"""
Chunking quality checks

Goal:
Validate that chunking produced coherent, useful, retrievable units of text
before we spend money/time embedding them.

1. Chunk count by source_type
Why:
Ensures one source type does not unexpectedly dominate or disappear.
Good:
Distribution roughly matches the corpus. Transcript-heavy is okay if the
course content is mostly transcript, but extreme dominance should be noted.

2. Chunk count by source_name
Why:
Catches source-level extraction issues, such as a PDF producing almost no chunks.
Good:
Each important source produces chunks. Image-heavy PDFs may produce few chunks,
which is expected but should be documented.

3. Chunk length distribution
Measure:
min, p25, median, mean, p75, p95, max character lengths.
Why:
Detects chunks that are too tiny to be meaningful or too large for precise retrieval.
Good:
Most chunks are near the intended splitter range. Very short chunks should be rare.
p95 should be close to, but not wildly above, configured chunk_size.

4. Junk-rate
Measure:
Percent of chunks that are empty, very short, mostly punctuation, or filler
such as "agenda", "thank you", "questions", "q&a".
Why:
Junk chunks waste embedding cost and can pollute retrieval.
Good:
Low junk rate, ideally <5%; <1–2% is excellent.

5. Metadata preservation
Why:
Metadata is needed for citations, debugging retrieval, filtering by source,
and understanding where answers came from.
Good:
Each chunk keeps source_type, source_name, page/section when available, topic,
and has added chunk_index/chunk_size.

6. Boundary quality spot check
Method:
Randomly inspect 20–30 chunks across source types.
Why:
Automated stats cannot tell whether chunks start/end in coherent places.
Good:
Chunks do not usually start mid-sentence, end mid-thought, or depend heavily
on missing previous context.

7. Coherence / answerability spot check
Method:
For random chunks, ask: "Could an LLM answer a useful question using only this?"
Why:
RAG quality depends on chunks carrying enough meaning independently.
Good:
Most chunks contain one coherent concept, explanation, or exchange.

8. Duplicate / overlap sanity
Why:
Overlap helps preserve context, but too much duplication increases embedding cost
and can crowd retrieval results with near-identical chunks.
Good:
Some repeated text between neighboring chunks is expected. Many near-identical
chunks or repeated headers/footers indicate excessive overlap or weak cleaning.

9. Sparse-source investigation
Why:
A source with unexpectedly few chunks may indicate failed extraction, image-heavy
slides, or over-aggressive cleaning.
Good:
Sparse sources are explainable. Example: image-heavy PDFs may correctly produce
few text chunks but should be flagged for future OCR/vision captioning.

10. Retrieval smoke test after embeddings
Method:
Ask 5–10 expected user questions and inspect the top-k retrieved chunks.
Why:
The real test of chunking is whether retrieval finds coherent chunks that answer
the question.
Good:
Top results contain the relevant explanation, not just keyword mentions.

---

Run from the repo root:
    uv run python 2_chunking/chunk.py

Reads:  output/documents.json
Writes: output/chunks.json
"""

import json
import sys
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).parent))

from langchain_core.documents import Document
from splitter_config import split_documents

INPUT_PATH = Path(__file__).parent.parent / "output" / "documents.json"
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "chunks.json"


def is_junk(text: str) -> bool:
    text = text.strip()
    return (
        not text
        or len(text.split()) < 8
        or sum(c.isalpha() for c in text) < 20
        or text.lower().strip(" .…!?") in {
            "agenda", "thank you", "questions", "q&a", "before we get started"
        }
    )


def load_documents(path: Path) -> list[Document]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Document(page_content=d["content"], metadata=d["metadata"]) for d in raw]


def chunk():
    print(f"📂 Loading documents from {INPUT_PATH}...")
    docs = load_documents(INPUT_PATH)
    print(f"   → {len(docs)} documents loaded")

    print("\n✂️  Splitting...")
    chunks = split_documents(docs)

    lengths = sorted(len(c.page_content) for c in chunks)
    p50 = int(median(lengths))
    p95 = lengths[int(len(lengths) * 0.95)]

    print(f"\n📊 Stats")
    print(f"   raw docs   : {len(docs):,}")
    print(f"   chunks     : {len(chunks):,}")
    print(f"   min length : {lengths[0]:,} chars")
    print(f"   max length : {lengths[-1]:,} chars")
    print(f"   avg length : {sum(lengths) // len(lengths):,} chars")
    print(f"   p50 length : {p50:,} chars")
    print(f"   p95 length : {p95:,} chars")
    junk = sum(1 for c in chunks if is_junk(c.page_content))
    print(f"   junk rate  : {junk}/{len(chunks)} ({100 * junk / len(chunks):.1f}%)")

    by_type: dict[str, int] = {}
    by_name: dict[str, int] = {}
    for c in chunks:
        t = c.metadata.get("source_type", "unknown")
        n = c.metadata.get("source_name", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
        by_name[n] = by_name.get(n, 0) + 1

    print("\n   by source_type:")
    for t, n in sorted(by_type.items()):
        print(f"     {t}: {n}")

    print("\n   by source_name:")
    for name, n in sorted(by_name.items()):
        print(f"     {name}: {n}")

    output = [{"content": c.page_content, "metadata": c.metadata} for c in chunks]
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\n✅ {len(chunks)} chunks saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    chunk()
