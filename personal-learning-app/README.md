# Personal Learning Journal

A Streamlit app that turns your raw learning materials into structured, insight-rich journal entries using Claude AI.

## What it does

Bring your own sources — PDFs, Zoom transcripts, lecture notes, pasted text — for any topic. The app generates:

- **Summary** — 3–5 crisp non-obvious insights
- **Journal** — flowing prose that captures the core mental model, written as expert reference notes for future recall
- **Key Concepts** — terms worth remembering
- **Resources** — papers, videos, and blogs worth going deeper on

Output is downloadable as Markdown.

## Setup

Requires [Claude Code CLI](https://claude.ai/code) to be installed and authenticated.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Stack

- Python + Streamlit
- SQLite (local, no server)
- Claude Sonnet 4.6 via `claude --print` CLI
- pypdf for PDF extraction
