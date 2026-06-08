"""
Run from the repo root:
    python 1_preprocessing/preprocess.py

Outputs: output/documents.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loaders.pdf_loader import load_pdfs
from loaders.transcript_loader import load_transcripts
from loaders.web_loader import load_from_course_structure

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "output"


def validate_loader_output(docs: list, label: str, failed: list[str] | None = None) -> None:
    print(f"   → {len(docs)} documents loaded")
    if failed:
        for url in failed:
            print(f"   ⚠️  failed to extract: {url}")

    if not docs:
        return

    lengths = [len(d.page_content) for d in docs]
    empty = sum(1 for l in lengths if l == 0)
    print(f"   content length — min: {min(lengths):,}  max: {max(lengths):,}  avg: {sum(lengths)//len(lengths):,} chars")
    if empty:
        print(f"   ⚠️  {empty} empty document(s)")

    sample = docs[0].metadata
    print(f"   metadata sample: {sample}")


def preprocess():
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_docs = []

    print("\n📄 Loading PDFs...")
    pdf_docs = load_pdfs(DATA_DIR / "pdfs")
    validate_loader_output(pdf_docs, "pdf")
    all_docs.extend(pdf_docs)

    print("\n🎙️  Loading transcripts...")
    transcript_docs = load_transcripts(DATA_DIR / "transcripts")
    validate_loader_output(transcript_docs, "transcript")
    all_docs.extend(transcript_docs)

    print("\n🌐 Loading web readings...")
    web_docs, web_failed = load_from_course_structure(DATA_DIR / "course_structure.yaml")
    validate_loader_output(web_docs, "web", failed=web_failed)
    all_docs.extend(web_docs)

    if not all_docs:
        print("\nNo documents found. Add files to data/ and re-run.")
        return

    output = [{"content": d.page_content, "metadata": d.metadata} for d in all_docs]
    out_path = OUTPUT_DIR / "documents.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print(f"\n✅ {len(all_docs)} documents saved to {out_path}")
    print("\nDocuments by source type:")
    by_type: dict[str, int] = {}
    for d in all_docs:
        t = d.metadata.get("source_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    for t, n in sorted(by_type.items()):
        print(f"   {t}: {n}")


if __name__ == "__main__":
    preprocess()
