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
| 5 — Chat UI | `5_chat/` | ✅ complete | `uv run python 5_chat/run_app.py` |

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
- Current provider: **OpenAI `text-embedding-3-small`** (`EMBEDDING_PROVIDER=openai` + `OPENAI_API_KEY` in `.env`)
- To swap back to local: set `EMBEDDING_PROVIDER=huggingface` in `.env`, re-run (uses `all-MiniLM-L6-v2`)
- Last run: **772 vectors** in ~4s; collection `course_rag` at `vector_store/`
- Fixes the `all-MiniLM-L6-v2` truncation issue: that model's effective `max_seq_length` is 256 tokens and silently truncated 521/772 chunks (67%, max chunk = 453 tokens); `text-embedding-3-small`'s 8191-token limit means no chunk is truncated
- ⚠️ Protobuf fix: `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` must be set before chromadb imports; hardcoded via `os.environ.setdefault` at top of `run_embeddings.py`; also in `.env`

## Stage 4 — Retrieval

- `4_retrieval/retriever_config.py` — loads Chroma with same embedding model; also provides `get_bm25_retriever()`, `get_bm25_results_with_scores()`, and `hybrid_search()` (RRF merge of semantic + BM25, tagged with origin "semantic"/"bm25"/"both")
- `4_retrieval/run_retrieval.py` — smoke test with 5 `SAMPLE_QUERIES` + 5 `HYBRID_EDGE_CASES`; K=5
- `4_retrieval/run_eval.py` / `run_rag_eval.py` / `build_comparison_csv.py` — full retrieval + generation comparison across semantic/BM25/hybrid/rewritten_reranked for all 10 questions; output in `output/retrieval_eval.json`, `output/rag_eval.json`, `output/retrieval_comparison.csv`
- Current mode: **hybrid (semantic + BM25 via RRF)** implemented and validated
- BM25 lexical normalization: `4_retrieval/bm25_normalizer.py` (`normalize_for_bm25` — lowercase + strip hyphens) + `4_retrieval/build_bm25_chunks.py` generates `output/chunks_bm25.json` (`output/chunks.json` untouched; same content with `metadata.normalized_text` added). `get_bm25_retriever()` indexes on `normalized_text` while returning original-cased `page_content`/metadata. Fixes case/hyphen variants (e.g. "BM25"/"bm25", "reranking"/"Re-ranking"/"RERANKING" all now score identically). BM25 still weaker than semantic on natural-language proper-noun queries (e.g. "Pinecone", instructor names) — see `output/retrieval_comparison.csv` for full per-question analysis.
- Re-run completed (2026-06-09) against OpenAI embeddings + normalized BM25 + inline-citation prompt: `output/retrieval_eval.json` (150 records), `output/rag_eval.json` (30 records, 27/30 with inline `(Source: ...)` citations), `output/retrieval_comparison.csv` (10 rows, verdicts refreshed). Pre-OpenAI-embedding versions backed up as `output/*_huggingface.{json,csv}`.
- **Known retrieval gap (Q4)**: for "What are good ways to judge whether an LLM output is correct?", none of semantic/BM25/hybrid surface the chunk that explicitly enumerates faithfulness/precision/NDCG/recall/MRR (`session2-week2-lecture-raw-transcript` · "Building a Golden Dataset for Evaluation"). Semantic doesn't rank it in the top 20 at all; BM25 ranks it #17 (K=5 cutoff). All three generations hedge into "cannot provide a definitive answer" as a result — confirmed as a retrieval miss, not a generation issue. Likely cause: conversational query phrasing doesn't embed/match closely to the corpus's technical metric-name framing.
- **Re-ranking + query rewriting (2026-06-10)**: built `4_retrieval/reranker_config.py` — `hybrid_search_reranked(query, k=5, candidate_k=20)` using cross-encoder `cross-encoder/ms-marco-MiniLM-L-6-v2` over `get_candidate_pool()` (deduped union of semantic top-`candidate_k` ∪ BM25 top-`candidate_k`, not an RRF merge — avoids RRF silently dropping high-single-retriever-rank chunks). Initial finding: cross-encoder reranking alone did **not** fix the Q4 gap — chunk #476 ("Building a Golden Dataset for Evaluation", which names precision/NDCG/recall/MRR) never appeared in semantic top-20 *or* BM25 top-20, so reranking never saw it (retrieval-coverage issue, not ranking).
- **Fix for Q4**: added `4_retrieval/query_rewriter.py` — `rewrite_query(question)` uses `gpt-4o-mini` to reformulate a conversational question into a keyword-dense search query using the corpus's technical terminology, preserving proper nouns. `hybrid_search_rewritten_reranked(query, k=5, candidate_k=20)` (in `reranker_config.py`) = `rewrite_query()` → `hybrid_search_reranked()`. Confirmed via `4_retrieval/run_rewrite_diagnostic.py` that this makes chunk #476 reachable for Q4 and produces a grounded (non-hedging) answer. `4_retrieval/run_rewrite_generation_compare.py` and `4_retrieval/run_force_include_check.py` are additional one-off diagnostics from this exploration (not part of the regular pipeline). `4_retrieval/run_rerank_diagnostic.py` / `run_rerank_generation_check.py` are the earlier rerank-only diagnostics.
- **Wired in as 4th method**: `run_eval.py` and `run_rag_eval.py` both support `ENABLE_REWRITE_RERANK=true` (env var, default off) to add `rewritten_reranked` as a 4th method alongside semantic/bm25/hybrid. With it enabled, `output/retrieval_eval.json` has 200 records (10 questions × 4 methods × k=5) and `output/rag_eval.json` has 40 records (10 questions × 4 methods). Pre-4-method versions backed up as `output/retrieval_eval_pre_ragas.json` / `output/rag_eval_pre_ragas.json`.
- **RAGAS quantitative evaluation (2026-06-10)**: added `ragas>=0.4` + `langchain-community<0.4` (pin required — ragas 0.4.3 hard-imports `langchain_community.chat_models.vertexai`, removed in langchain-community 0.4+) to the `embeddings` extra in `pyproject.toml`. Built `output/golden_dataset.json` (10 `{question, reference}` entries grounded in `output/chunks.json`, one per SAMPLE_QUERY/HYBRID_EDGE_CASE — **reviewed and approved by the user, 2026-06-10**). `4_retrieval/run_ragas_eval.py` scores (question, method) records from `rag_eval.json` against the golden references using ragas 0.4.3's collections API (`Faithfulness`, `AnswerRelevancy`, `ContextRecall`, judge=`gpt-4o-mini`, embeddings=`text-embedding-3-small`). Each metric call is slow (~60-80s, multi-step LLM pipelines) and prone to OpenAI TPM rate limits at concurrency > 1, so the script runs fully sequential (`MAX_RETRIES=3`, `PER_RECORD_TIMEOUT=240s`) and **writes `output/ragas_eval.json` incrementally after every record** with resume support (skips `(question, method)` pairs already scored) — a single record's failure is recorded with `null` scores + `error` field rather than crashing the run.
  - **Scope (per user request, reduced from the original 10×4 plan)**: only the 5 `SAMPLE_QUERIES` (20 records = 5 questions × 4 methods) and 3 metrics (`context_precision` dropped — was the slowest, per-chunk-scored metric). `HYBRID_EDGE_CASES` (5 more questions) and `context_precision` are not yet scored.
  - **Results** (`output/ragas_summary.csv`, mean over 5 questions):

    | method | faithfulness | answer_relevancy | context_recall |
    |---|---|---|---|
    | semantic | 0.9214 | 0.7891 | 0.7600 |
    | bm25 | 0.9800 | 0.7338 | 1.0000 |
    | hybrid | 0.9500 | 0.7891 | 0.7500 |
    | **rewritten_reranked** | **0.9818** | **0.9176** | **1.0000** |

  - **`rewritten_reranked` wins on every metric.** Strongest signal: for Q4, `semantic`/`hybrid` both score `answer_relevancy=0.0, context_recall=0.0` (RAGAS zeroes the "cannot provide a definitive answer" hedge as noncommittal), while `rewritten_reranked` scores `faithfulness=1.0, answer_relevancy=0.99, context_recall=1.0` — it retrieves the right chunk and gives a grounded answer where the baseline gives up.
  - `bm25` scores `answer_relevancy=0.0` for "What components do agentic AI systems need?" despite `faithfulness=1.0, context_recall=1.0` — same noncommittal-hedge pattern as Q4 (bm25 also misses the relevant chunk and hedges into "cannot provide a definitive answer" for this question), not a separate anomaly.
- **`build_comparison_csv.py` refreshed for 4 methods (2026-06-10)**: added a `rewritten_reranked` entry + updated `winner`/`why` for all 10 questions in `ANALYSIS`, incorporating the RAGAS scores above for the 5 `SAMPLE_QUERIES`. `output/retrieval_comparison.csv` now has a `Rewritten+Reranked` column (7 columns total); old 3-method version backed up as `output/retrieval_comparison_3method.csv`. Headlines: `rewritten_reranked` is now sole/joint winner on Q2 (adds the previously-missing Query/Key/Value attention detail) and Q4 (resolves the hedge); ties with semantic on the 4 `HYBRID_EDGE_CASES` proper-noun/BM25-failure questions (Q6-8, Q10) by retrieving the same key chunks via the rewritten query; the one regression is Q3 ("How do prompts influence model behavior?"), where the rewritten query drifts toward "agent" framing and misses the prompt-engineering chunks (RAGAS answer_relevancy 0.79, lowest of the four) — semantic remains the winner there.

## Stage 5 — Chat UI

- `5_chat/generator.py` — `generate(query, history=None, k=5)` → `(answer, results)`; retrieval via `hybrid_search_rewritten_reranked()` (per RAGAS recommendation), generation via `gpt-4o-mini` (chosen over `langchain-anthropic` since no Anthropic API key is configured). `results: List[Tuple[Document, origin_str, rerank_score, sem_score]]`.
- **Conversational follow-ups (2026-06-11)**: `4_retrieval/query_rewriter.py` adds `contextualize_query(history, question)` — uses `gpt-4o-mini` + prior turns to rewrite a follow-up (e.g. "How does it compare to fine-tuning?") into a standalone question before it goes through `rewrite_query()`/`hybrid_search_rewritten_reranked()`. `generate()` also passes `history` (list of `{"role", "content"}` dicts) into the generation messages so the final answer can resolve pronouns/implicit references too. Verified via a 2-turn CLI test ("What is RAG?" → "How does it compare to fine-tuning?") and confirmed working in the Streamlit UI.
- `5_chat/app.py` — Streamlit chat UI: inline `[Source N]` citations in the answer, collapsible "Sources" expander showing source name/page/speaker + content preview per chunk. Builds `history` from `st.session_state.messages[:-1]` (full conversation so far, no cap) and passes it to `generate()`. Sidebar shows the "Mastering Agentic AI" Gen Academy certification banner (`5_chat/assets/gen_academy_banner.png`).
- `5_chat/run_app.py` — **launcher, use this instead of `streamlit run app.py`**. `streamlit run` imports streamlit (and its protobuf-based deps via chromadb's opentelemetry exporter) before the app script runs, so `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` set inside `app.py` is too late and causes `TypeError: Descriptors cannot be created directly`. `run_app.py` sets the env var first, then invokes `streamlit.web.cli`.
- `5_chat/run_chat.py` — CLI smoke-test harness for the generator; accumulates `history` across the input loop (mirrors `app.py`) so multi-turn follow-ups can be tested without launching the UI.
- Run: `uv run python 5_chat/run_app.py` (requires `uv sync --extra chat` first if not already synced). Confirmed working end-to-end by the user (2026-06-10).

---

## Observability — LangSmith

- Tracing enabled via `.env`: `LANGCHAIN_TRACING_V2=true`, `LANGSMITH_API_KEY=lsv2_...`, `LANGCHAIN_PROJECT=course-rag`. Picked up automatically by any module that calls `load_dotenv()` (directly or transitively) before invoking a LangChain `ChatOpenAI`.
- **Two projects**: live chat traces (`5_chat/`) go to `course-rag`. Eval-script traces (`4_retrieval/run_eval.py`, `run_rag_eval.py`, `run_ragas_eval.py`) override `os.environ["LANGCHAIN_PROJECT"] = "course-rag-eval"` after `load_dotenv()`, so repeated eval runs don't clutter the live-chat project.
- `run_ragas_eval.py` calls RAGAS via a raw `openai.AsyncOpenAI` client (not a LangChain `Runnable`), so `LANGCHAIN_TRACING_V2` alone wouldn't trace those judge/embedding calls — wrapped with `langsmith.wrappers.wrap_openai(AsyncOpenAI())` to capture them too.
- Confirmed working end-to-end by the user (2026-06-11): traces visible in both `course-rag` and `course-rag-eval` projects in the LangSmith UI.

---

## Unresolved / Not started

- **Image OCR / vision captions for `Week 2- Session 2.pdf`** — only 1 chunk retrieved across the full eval set, likely mostly diagrams. Future: `pytesseract` / `pdf2image` / Claude vision to extract slide images as additional documents.
- **`.md` file loader** — user mentioned `.md` notes files. Need to ask: where are they? Then add `1_preprocessing/loaders/markdown_loader.py`, `source_type: "markdown"`, integrate into `preprocess.py`.

---

## Next steps in order

1. **RAGAS — decide whether to extend coverage**: current `output/ragas_eval.json`/`ragas_summary.csv` cover only 5/10 questions (`SAMPLE_QUERIES`) and 3/4 metrics (`context_precision` dropped for speed). `rewritten_reranked` already wins decisively on all 3 scored metrics. Optionally: (a) run the remaining 5 `HYBRID_EDGE_CASES` questions, and/or (b) add `context_precision` back — `run_ragas_eval.py`'s resume logic means this can be done incrementally without re-scoring existing records.
