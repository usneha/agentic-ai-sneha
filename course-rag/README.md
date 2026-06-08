# 🧠 Course RAG — Mastering Agentic AI

A Retrieval-Augmented Generation (RAG) system that lets you chat with all the material from the *Mastering Agentic AI* course — slides, Zoom transcripts, and blog posts — in one conversational interface.

---

## 🗺️ Roadmap

| Stage | Folder | Description | Status |
|-------|--------|-------------|--------|
| 1 | `1_preprocessing/` | Load all course sources → raw documents | ✅ Done |
| 2 | `2_embeddings/` | Chunk + embed → Chroma vector store | 🔜 Next |
| 3 | `3_retrieval/` | Hybrid semantic + keyword retrieval | 🔜 Soon |
| 4 | `4_chatbot/` | Streamlit chat UI + Claude generation | 🔜 Soon |

---

## 🏗️ Architecture

```
data/
├── pdfs/          ← course slides (exported from Google Slides)
├── transcripts/   ← Zoom session transcripts (.vtt or .txt)
└── urls.txt       ← blog posts and reading links

      ↓ Stage 1: preprocess.py

output/documents.json ← raw extracted documents with metadata

      ↓ Stage 2: chunk + embed
      
vector_store/      ← Chroma DB (persisted embeddings)

      ↓ Stages 3 & 4

Streamlit chatbot  ← conversational Q&A over all course material
```

---

## ⚡ Quick Start

```bash
# 1. Install uv (if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install Stage 1 dependencies
uv sync

# 3. Add your course material
#    - Drop PDFs into data/pdfs/
#    - Drop Zoom transcripts (.vtt or .txt) into data/transcripts/
#    - Add blog URLs to data/urls.txt (one per line)

# 4. Run preprocessing
uv run python 1_preprocessing/preprocess.py
```

Output is written to `output/documents.json`.

### Installing later stages

```bash
uv sync --extra embeddings   # Stage 2
uv sync --extra chat         # Stage 3
uv sync --all-extras         # Everything
```

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `langchain` | Core RAG orchestration |
| `langchain-community` | Document loaders (PDF, web) |
| `langchain-text-splitters` | Recursive character splitting |
| `pdfplumber` | High-fidelity PDF text extraction |
| `trafilatura` | Clean article extraction from web URLs |
| `python-dotenv` | API key management via `.env` |
| `langchain-openai` *(stage 2)* | `text-embedding-3-small` embeddings |
| `chromadb` *(stage 2)* | Local vector store with persistence |
| `langchain-anthropic` *(stage 4)* | Claude generation via Anthropic SDK |
| `streamlit` *(stage 4)* | Conversational chat UI |

---

## 🔑 Environment Setup

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

```
OPENAI_API_KEY=...      # needed from Stage 2 (embeddings)
ANTHROPIC_API_KEY=...   # needed from Stage 4 (generation)
```
