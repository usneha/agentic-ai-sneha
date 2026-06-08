# Stage 1 — Preprocessing

This stage loads course material from three source types, extracts clean text, and splits it into chunks with metadata. The output is a JSON file ready to be embedded in Stage 2.

---

## 📂 Sources Handled

| Source | Input | Loader | Chunk Strategy |
|--------|-------|--------|----------------|
| Slides / PDFs | `data/pdfs/*.pdf` | `PDFPlumberLoader` | Per-page, then 800-token chunks |
| Zoom transcripts | `data/transcripts/*.vtt` or `*.txt` | Custom parser | Per-speaker utterance, merged if short |
| Blogs / web | `data/urls.txt` | `trafilatura` | 1000-token chunks |

---

## 🗂️ File Structure

```
1_preprocessing/
├── loaders/
│   ├── pdf_loader.py          ← loads all PDFs from data/pdfs/
│   ├── transcript_loader.py   ← parses Zoom VTT and plain-text transcripts
│   └── web_loader.py          ← fetches and extracts text from URLs
└── preprocess.py              ← orchestrator: runs all loaders → saves raw documents
```

> Chunking lives in Stage 2 (`2_embeddings/`) so you can tune chunk size and overlap alongside the embedding model without re-running the loaders.

---

## ▶️ Running

```bash
# From the repo root
python 1_preprocessing/preprocess.py
```

Sample output:

```
📄 Loading PDFs...
  Loading week1_intro.pdf...
    → 24 pages
  Loading week2_transformers.pdf...
    → 31 pages

🎙️  Loading transcripts...
  Loading session1.vtt...
    → 142 utterance chunks

🌐 Loading web URLs...
  Fetching https://jalammar.github.io/illustrated-transformer/...
    → 24,277 chars
  Fetching https://arxiv.org/pdf/1706.03762...
    → PDF: 15 pages

✅ 236 documents saved to output/documents.json

Documents by source type:
   pdf: 189
   transcript: 98
   web: 25
```

---

## 📄 Output Format

Each entry in `output/chunks.json`:

```json
{
  "content": "Attention is a mechanism that allows the model to...",
  "metadata": {
    "source_type": "pdf",
    "source_name": "week2_transformers.pdf",
    "page": 7
  }
}
```

Transcript chunks also include `speaker` and `timestamp_start`. Web chunks include `url`.

---

## 📝 Transcript Format Support

Two Zoom export formats are detected automatically:

**WebVTT** (`.vtt` or any file starting with `WEBVTT`):
```
WEBVTT

00:00:01.000 --> 00:00:05.000
Instructor: Today we're covering attention mechanisms.
```

**Plain text** (Zoom's `.txt` download):
```
Instructor  0:00:01
Today we're covering attention mechanisms.
```

Consecutive short utterances from the same speaker are merged to avoid tiny, context-poor chunks.

---

## ⚙️ Tuning Chunk Sizes

Edit the constants at the top of `splitter.py`:

| Source | `chunk_size` | `chunk_overlap` | Rationale |
|--------|-------------|-----------------|-----------|
| PDF | 800 | 100 | Slide pages are dense; smaller chunks = more precise retrieval |
| Web | 1000 | 150 | Articles have more prose; larger chunks preserve flow |
| Transcript | 600 | 50 | Utterances are natural units; only split very long monologues |
