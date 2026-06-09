# course-rag — Project Handoff

**Goal:** RAG system + Streamlit chatbot for *Mastering Agentic AI* course material (PDFs, Zoom transcripts, blog URLs, .md notes). 4-stage pipeline: load → chunk+embed → retrieve → chat.

---

## What's working (Stage 1 complete)

- `uv` for package management; `pyproject.toml` has optional dep groups per stage (`embeddings`, `chat`)
- `.python-version` pins to 3.12 (system Python 3.9 is x86, breaks on arm64 Mac)
- `1_preprocessing/loaders/pdf_loader.py` — loads all PDFs from `data/pdfs/` via PDFPlumberLoader; FontBBox warnings suppressed
- `1_preprocessing/loaders/transcript_loader.py` — parses Zoom VTT and plain-text formats; merges short consecutive same-speaker utterances
- `1_preprocessing/loaders/web_loader.py` — routes PDF URLs (`.pdf` ext or `/pdf/` path) to PDFPlumberLoader via tempfile; HTML URLs to trafilatura
- `1_preprocessing/preprocess.py` — orchestrator; writes `output/documents.json` (no chunking here)
- `splitter.py` (repo root) — source-aware splitter for Stage 2; PDF 800/100, web 1000/150, transcript 600/50
- Last successful run: **204 documents** (193 pdf, 11 web) → `output/documents.json`
- Run: `uv run python 1_preprocessing/preprocess.py`

---

## Unresolved / Not started

- **Image OCR / vision captions for `Week 2- Session 2.pdf`** — only 7 chunks from 28 pages, likely mostly diagrams/images that PDFPlumber skips. Future: use a vision model or OCR (e.g. `pytesseract`, `pdf2image`, or Claude vision) to extract text from slide images and add as additional documents.
- **`.md` file loader** — user mentioned `.md` notes files but was cut off. Need to ask: where are they, what do they contain? Then add `1_preprocessing/loaders/markdown_loader.py`, `source_type: "markdown"`, integrate into `preprocess.py`.
- **`data/transcripts/`** — empty; no Zoom files added yet. Loader is ready.
- **Stage 2** — waiting on OpenAI API credits for `text-embedding-3-small`. `splitter.py` is ready. Need `2_embeddings/embed.py`: reads `output/documents.json` → splits → embeds → writes Chroma to `vector_store/`. HuggingFace `all-MiniLM-L6-v2` available as free fallback.
- **Stage 3** — hybrid BM25 + Chroma semantic retrieval, optional reranking.
- **Stage 4** — Streamlit conversational chat UI. Claude (`claude-opus-4-8` via `langchain-anthropic`). **No sidebar filters** — clean chat only. Inline source citations as collapsible expander.

---

## Next steps in order

1. Ask about `.md` files → add `markdown_loader.py` → re-run `preprocess.py`
2. When OpenAI credits arrive: `uv sync --extra embeddings` → build + run `2_embeddings/embed.py`
3. Build Stage 3 retrieval, then Stage 4 chatbot
