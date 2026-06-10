# course-rag — Project Handoff

**Goal:** RAG system + Streamlit chatbot for *Mastering Agentic AI* course material (PDFs, Zoom transcripts, blog URLs, .md notes). 5-stage pipeline: preprocess → chunk → embed → retrieve → chat.

---

## Pipeline status

| Stage | Folder | Status | Run command |
|-------|--------|--------|-------------|
| 1 — Preprocess | `1_preprocessing/` | ✅ complete | `uv run python 1_preprocessing/preprocess.py` |
| 2 — Chunk | `2_chunking/` | ✅ complete | `uv run python 2_chunking/run_chunking.py` |
| 3 — Embed | `3_embeddings/` | ✅ complete | `uv run python 3_embeddings/run_embeddings.py` |
| 4 — Retrieve | `4_retrieval/` | ✅ complete | `uv run python 4_retrieval/run_retrieval.py` |
| 5 — Chat UI | `5_chat/` | ⬜ not started | — |

---

## Stage 1 — Preprocessing

- `1_preprocessing/loaders/pdf_loader.py` — loads all PDFs from `data/pdfs/` via PDFPlumberLoader; FontBBox warnings suppressed
- `1_preprocessing/loaders/transcript_loader.py` — parses VTT, bracketed `[Speaker] HH:MM:SS`, plain `Speaker  HH:MM:SS`, and speaker-block (name on its own line) formats; merges short consecutive same-speaker utterances
- `1_preprocessing/loaders/web_loader.py` — routes PDF URLs to PDFPlumberLoader via tempfile; HTML URLs to trafilatura
- `1_preprocessing/cleaner.py` — filters short/low-value docs after loading (min 40 chars, low-value phrase list)
- `1_preprocessing/preprocess.py` — orchestrator; writes `output/documents.json`
- Last run: **208 documents** (113 pdf, 93 transcript_chapter, 2 web) after cleaning — transcripts are now grouped into per-chapter documents (was 887 utterance-level `transcript` docs)

## Stage 2 — Chunking

- `2_chunking/splitter_config.py` — source-aware splitters: PDF 800/100, web 1000/150, transcript 900/120; fallback 1000/150 for unknown types with warning
- `2_chunking/run_chunking.py` — orchestrator with full stats: count, length distribution, p50/p95, junk rate, by source_type, by source_name
- Last run: **772 chunks** (184 pdf, 557 transcript_chapter, 31 web); junk rate 0%; p50=1349, p95=1493 chars — chapter-based transcript chunking replaced the old 1420-chunk utterance-level approach

## Stage 3 — Embeddings

- `3_embeddings/embedder_config.py` — `get_embeddings()` factory; reads `EMBEDDING_PROVIDER` env var
- `3_embeddings/run_embeddings.py` — reads `output/chunks.json` → embeds → persists Chroma to `vector_store/`
- Current provider: **HuggingFace `all-MiniLM-L6-v2`** (local, no API key)
- To swap to OpenAI: set `EMBEDDING_PROVIDER=openai` and `OPENAI_API_KEY=sk-...` in `.env`, re-run
- Last run: **772 vectors** in ~4-7s; collection `course_rag` at `vector_store/`
- ⚠️ Protobuf fix: `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` must be set before chromadb imports; hardcoded via `os.environ.setdefault` at top of `run_embeddings.py`; also in `.env`

## Stage 4 — Retrieval

- `4_retrieval/retriever_config.py` — loads Chroma with same embedding model; also provides `get_bm25_retriever()`, `get_bm25_results_with_scores()`, and `hybrid_search()` (RRF merge of semantic + BM25, tagged with origin "semantic"/"bm25"/"both")
- `4_retrieval/run_retrieval.py` — smoke test with 5 `SAMPLE_QUERIES` + 5 `HYBRID_EDGE_CASES`; K=5
- `4_retrieval/run_eval.py` / `run_rag_eval.py` / `build_comparison_csv.py` — full retrieval + generation comparison across semantic/BM25/hybrid for all 10 questions; output in `output/retrieval_eval.json`, `output/rag_eval.json`, `output/retrieval_comparison.csv`
- Current mode: **hybrid (semantic + BM25 via RRF)** implemented and validated
- BM25 lexical normalization: `4_retrieval/bm25_normalizer.py` (`normalize_for_bm25` — lowercase + strip hyphens) + `4_retrieval/build_bm25_chunks.py` generates `output/chunks_bm25.json` (`output/chunks.json` untouched; same content with `metadata.normalized_text` added). `get_bm25_retriever()` indexes on `normalized_text` while returning original-cased `page_content`/metadata. Fixes case/hyphen variants (e.g. "BM25"/"bm25", "reranking"/"Re-ranking"/"RERANKING" all now score identically). BM25 still weaker than semantic on natural-language proper-noun queries (e.g. "Pinecone", instructor names) — see `output/retrieval_comparison.csv` for full per-question analysis.
- Note: `retrieval_eval.json` / `rag_eval.json` / `retrieval_comparison.csv` were generated **before** this normalization fix — re-run `run_eval.py` / `run_rag_eval.py` / `build_comparison_csv.py` to refresh if needed.

---

## Unresolved / Not started

- **Stage 5 — Chat UI** — Streamlit conversational UI. Use `claude-sonnet-4-6` (or `claude-opus-4-8`) via `langchain-anthropic`. **No sidebar filters** — clean chat only. Inline source citations as collapsible expander. Run: `uv sync --extra chat` first.
- **Image OCR / vision captions for `Week 2- Session 2.pdf`** — only 1 chunk retrieved across the full eval set, likely mostly diagrams. Future: `pytesseract` / `pdf2image` / Claude vision to extract slide images as additional documents.
- **`.md` file loader** — user mentioned `.md` notes files. Need to ask: where are they? Then add `1_preprocessing/loaders/markdown_loader.py`, `source_type: "markdown"`, integrate into `preprocess.py`.
- **OpenAI embeddings** — credits pending. When ready: set `EMBEDDING_PROVIDER=openai` + `OPENAI_API_KEY` in `.env`, re-run Stage 3, rebuild vector store, re-run Stage 4 smoke test.

---

## Next steps in order

1. Build `5_chat/` — Streamlit chatbot with Claude, clean chat UI, collapsible source citations
2. When OpenAI credits arrive — swap embedding provider and rebuild vector store
