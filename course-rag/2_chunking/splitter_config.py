from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# PDFs from slides tend to have dense, self-contained pages — smaller chunks work better
_PDF_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    separators=["\n\n", "\n", ". ", " ", ""],
)

# Blog posts and articles are more prose-heavy — slightly larger chunks preserve context
_WEB_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""],
)

# Transcript utterances are already natural speech units; only split very long ones
_TRANSCRIPT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=900,
    chunk_overlap=120,
    separators=["\n\n", "\n", ". ", " ", ""],
)

_SPLITTER_MAP = {
    "pdf": _PDF_SPLITTER,
    "web": _WEB_SPLITTER,
    "transcript": _TRANSCRIPT_SPLITTER,
}

_FALLBACK_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def split_documents(docs: list[Document]) -> list[Document]:
    chunks = []
    for source_type, splitter in _SPLITTER_MAP.items():
        subset = [d for d in docs if d.metadata.get("source_type") == source_type]
        if subset:
            chunks.extend(splitter.split_documents(subset))

    unknown = [d for d in docs if d.metadata.get("source_type") not in _SPLITTER_MAP]
    if unknown:
        types = {d.metadata.get("source_type") for d in unknown}
        print(f"  ⚠️  Unknown source_type(s) {types} — using fallback splitter for {len(unknown)} docs")
        chunks.extend(_FALLBACK_SPLITTER.split_documents(unknown))

    return chunks
