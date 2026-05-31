# Learning Journal — Design Spec
**Date:** 2026-05-30  
**Status:** Approved

---

## What We're Building

A personal learning journal app. The user brings their own materials (Zoom transcripts, PDFs, course notes, articles, raw notes) for a topic, and the app generates a structured journal: a summary, a personal narrative explanation, key concepts, and curated resources. The output is downloadable. Progress is tracked per topic.

This replaces the current "Learning OS" (tracker + AI plan generator) with a resource-first, journal-first model.

---

## Core User Flow

1. **First launch:** User is prompted to complete a one-time profile (see User Profile below) before any topics are created
2. User clicks **+ New Topic** → modal asks for topic name → creates a new topic tab
3. User uploads files (PDF, DOCX, TXT, MD) and/or pastes text in batch → clicks **Generate Journal**
4. App sends all sources + topic name + user profile to Claude (via `claude --print` CLI) → returns structured JSON
5. Journal renders in a TOC + scrollable doc layout: Summary, Journal, Key Concepts, Resources
6. User can **Download Journal** as a markdown file
7. User can add more sources later and regenerate

---

## Layout

**Top nav:** Logo on the left. Settings icon (⚙) on the right — opens profile editor.

**Topic tabs row:** One pill per topic, horizontally scrollable. Active topic is highlighted. Last tab is always **+ New Topic** (dashed, blue).

**Per-topic view — two panels:**
- **Left (TOC, 180px):** Contents links (Summary, Journal, Key Concepts, Resources) + Sources list with type badges + Download button
- **Right (journal, flex):** Scrollable document with color-coded section labels

**Section color coding:**
- Summary → blue (`#3b5bdb`)
- Journal → purple (`#7b2d8b`)  
- Key Concepts → green (`#276138`)
- Resources → amber (`#92670a`)

---

## User Profile

Shown once on first launch (before any topics). Stored globally in SQLite. Editable later via a Settings icon in the nav.

**Fields:**

| Field | Type | Purpose |
|---|---|---|
| Background | Text (2-3 sentences) | Who you are, domain expertise (e.g. "Senior data scientist, strong in Python and stats, weak in frontend") |
| Explanation style | Multi-select | "Use analogies", "Show the math", "Connect to real examples", "Be concise", "Give me the intuition first" |
| Detail level | Radio | Concise (key points only) / Standard (balanced depth) / Deep (comprehensive, don't skip anything) |

**How it's used in generation:** The profile is injected into the Claude system prompt for the Journal section only. Summary and Key Concepts are always generated at a consistent technical level. Resources are always curated from the sources.

Example system prompt injection:
```
The user's background: [background text]
Explanation preferences: [selected styles]
Detail level: [concise|standard|deep]

Write the Journal section as a personal explanation tailored to this person. 
Match their background — don't explain things they already know well. 
Use their preferred explanation style.
```

---

## New Topic Modal

Triggered by clicking **+ New Topic** tab.

Fields:
- Topic name (text input, required)
- File upload (drag-and-drop zone, multi-file, accepts PDF/DOCX/TXT/MD)
- Paste text area (freeform, for Zoom transcripts, raw notes, etc.)
- File list (shows queued files with type badge + remove button)
- **Generate Journal** button (disabled until topic name + at least one source)

---

## Journal Generation

**Input to Claude:**
- Topic name
- All source texts concatenated with separators and labels (e.g. `--- Source: zoom_apr14.txt ---`)
- System prompt instructing Claude to return a JSON object with the schema below

**Output schema:**
```json
{
  "summary": "string (3-5 key points, technical but clear)",
  "journal": "string (narrative explanation written as if explaining to self, no dumbing down)",
  "concepts": ["string"],
  "resources": [{"title": "string", "type": "string", "description": "string"}]
}
```

**Execution:** `claude --print --output-format text --model claude-sonnet-4-6` via subprocess (same pattern as current `ai_helper.py`). No API key needed — uses Claude Code CLI authentication.

**Error handling:** If Claude returns malformed JSON or the CLI fails, show an inline error with a Retry button.

---

## Download

Clicking **Download Journal** generates a `.md` file with the following structure:

```
# [Topic Name]
Generated: [date]
Sources: [list of source names]

## Summary
...

## Journal
...

## Key Concepts
- concept 1
- concept 2

## Resources
- **Title** · type — description
```

Delivered as a browser download via Streamlit's `st.download_button`.

---

## Data Model

SQLite database, two tables:

```sql
CREATE TABLE profile (
  id INTEGER PRIMARY KEY DEFAULT 1,   -- single row
  background TEXT NOT NULL DEFAULT '',
  explanation_styles TEXT NOT NULL DEFAULT '[]',  -- JSON array of selected style strings
  detail_level TEXT NOT NULL DEFAULT 'standard',  -- 'concise' | 'standard' | 'deep'
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE topics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  sources TEXT NOT NULL DEFAULT '[]',   -- JSON array of {name, type, content}
  journal TEXT NOT NULL DEFAULT '{}',   -- JSON: {summary, journal, concepts, resources}
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
```

Sources are stored as JSON in the `sources` column (text content inline, not as file paths — keeps it self-contained).

---

## Tech Stack

- **Python + Streamlit** (existing)
- **SQLite** (existing pattern from current app)
- **Claude Code CLI** (`claude --print`) for journal generation — no API key needed
- No new dependencies required

---

## Out of Scope

- Mobile layout
- User accounts / multi-user
- Editing the generated journal inline
- Source versioning / diff when regenerating
- Search across topics
