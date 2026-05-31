# Learning Journal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing Learning OS app with a resource-first learning journal that accepts uploaded materials, generates a personalized AI journal per topic, and lets the user download it.

**Architecture:** Three focused modules — `database.py` (SQLite, profile + topics tables), `journal_generator.py` (Claude CLI subprocess), `app.py` (Streamlit UI: profile setup, topic tabs, new topic modal, journal view). The existing `app.py`, `database.py`, `ai_helper.py`, and `card_list.py` are fully replaced.

**Tech Stack:** Python 3, Streamlit ≥1.35, SQLite, Claude Code CLI (`claude --print`)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `database.py` | Replace | `profile` + `topics` tables, all CRUD |
| `journal_generator.py` | Create | Claude CLI subprocess call, prompt construction |
| `app.py` | Replace | Full Streamlit UI |
| `ai_helper.py` | Delete | Replaced by `journal_generator.py` |
| `card_list.py` | Delete | No longer needed |
| `tests/test_database.py` | Create | DB unit tests |
| `tests/test_journal_generator.py` | Create | Generator unit tests |

---

## Task 1: Project cleanup and test scaffolding

**Files:**
- Delete: `ai_helper.py`, `card_list.py`
- Create: `tests/__init__.py`
- Create: `tests/test_database.py`
- Create: `tests/test_journal_generator.py`

- [ ] **Step 1: Delete old files**

```bash
cd /Users/iupadhyayul/sneha-cursor/personal-learning-app
rm ai_helper.py card_list.py
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 2: Create test skeletons**

Create `tests/test_database.py`:
```python
import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Each test gets a fresh in-memory DB at a temp path."""
    monkeypatch.setenv("LEARNING_DB_PATH", str(tmp_path / "test.db"))
    import importlib
    import database
    importlib.reload(database)
    database.init_db()
    return database


def test_profile_default(db):
    profile = db.get_profile()
    assert profile is None


def test_save_and_get_profile(db):
    db.save_profile("I am a data scientist", ["Use analogies", "Show the math"], "standard")
    profile = db.get_profile()
    assert profile["background"] == "I am a data scientist"
    assert "Use analogies" in profile["explanation_styles"]
    assert profile["detail_level"] == "standard"


def test_create_and_get_topic(db):
    topic_id = db.create_topic("Transformer Architecture")
    topics = db.get_all_topics()
    assert len(topics) == 1
    assert topics[0]["name"] == "Transformer Architecture"
    assert topics[0]["id"] == topic_id


def test_add_sources_to_topic(db):
    topic_id = db.create_topic("Causal Inference")
    db.add_sources(topic_id, [{"name": "notes.txt", "type": "TXT", "content": "some text"}])
    topic = db.get_topic(topic_id)
    assert len(topic["sources"]) == 1
    assert topic["sources"][0]["name"] == "notes.txt"


def test_save_journal(db):
    topic_id = db.create_topic("Bayesian Methods")
    journal = {"summary": "s", "journal": "j", "concepts": ["c1"], "resources": []}
    db.save_journal(topic_id, journal)
    topic = db.get_topic(topic_id)
    assert topic["journal"]["summary"] == "s"


def test_delete_topic(db):
    topic_id = db.create_topic("To Delete")
    db.delete_topic(topic_id)
    assert db.get_topic(topic_id) is None
```

Create `tests/test_journal_generator.py`:
```python
import pytest
from unittest.mock import patch, MagicMock


def test_build_prompt_includes_topic():
    from journal_generator import build_prompt
    profile = {"background": "DS expert", "explanation_styles": ["Show the math"], "detail_level": "deep"}
    sources = [{"name": "notes.txt", "type": "TXT", "content": "attention is all you need"}]
    prompt = build_prompt("Transformers", sources, profile)
    assert "Transformers" in prompt
    assert "attention is all you need" in prompt
    assert "DS expert" in prompt
    assert "deep" in prompt


def test_build_prompt_no_profile():
    from journal_generator import build_prompt
    sources = [{"name": "notes.txt", "type": "TXT", "content": "some content"}]
    prompt = build_prompt("Topic", sources, None)
    assert "Topic" in prompt
    assert "some content" in prompt


def test_parse_response_valid():
    from journal_generator import parse_response
    raw = '{"summary": "s", "journal": "j", "concepts": ["c1"], "resources": []}'
    result = parse_response(raw)
    assert result["summary"] == "s"
    assert result["concepts"] == ["c1"]


def test_parse_response_with_markdown_fence():
    from journal_generator import parse_response
    raw = '```json\n{"summary": "s", "journal": "j", "concepts": [], "resources": []}\n```'
    result = parse_response(raw)
    assert result["summary"] == "s"


def test_parse_response_invalid_returns_error():
    from journal_generator import parse_response
    result = parse_response("not json at all")
    assert "error" in result


def test_generate_journal_calls_claude():
    from journal_generator import generate_journal
    profile = {"background": "expert", "explanation_styles": [], "detail_level": "standard"}
    sources = [{"name": "f.txt", "type": "TXT", "content": "content"}]
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"summary":"s","journal":"j","concepts":[],"resources":[]}'
    with patch("journal_generator.subprocess.run", return_value=mock_result) as mock_run:
        result = generate_journal("Topic", sources, profile)
    assert mock_run.called
    assert result["summary"] == "s"


def test_generate_journal_cli_error():
    from journal_generator import generate_journal
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "CLI failed"
    with patch("journal_generator.subprocess.run", return_value=mock_result):
        result = generate_journal("Topic", [], None)
    assert "error" in result
```

- [ ] **Step 3: Run tests — expect failures (modules don't exist yet)**

```bash
cd /Users/iupadhyayul/sneha-cursor/personal-learning-app
.venv/bin/pytest tests/ -v 2>&1 | head -40
```

Expected: ImportError / ModuleNotFoundError for `database` and `journal_generator`.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: add test skeletons for database and journal_generator"
```

---

## Task 2: Database layer

**Files:**
- Replace: `database.py`

- [ ] **Step 1: Replace database.py**

```python
import sqlite3
import json
import os
import time
from pathlib import Path

DB_PATH = Path(os.getenv("LEARNING_DB_PATH", str(Path(__file__).parent / "data" / "learning.db")))


def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY DEFAULT 1,
            background TEXT NOT NULL DEFAULT '',
            explanation_styles TEXT NOT NULL DEFAULT '[]',
            detail_level TEXT NOT NULL DEFAULT 'standard',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sources TEXT NOT NULL DEFAULT '[]',
            journal TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_profile() -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["explanation_styles"] = json.loads(d["explanation_styles"])
    return d


def save_profile(background: str, explanation_styles: list[str], detail_level: str):
    now = int(time.time() * 1000)
    conn = get_connection()
    conn.execute("""
        INSERT INTO profile (id, background, explanation_styles, detail_level, created_at, updated_at)
        VALUES (1, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            background=excluded.background,
            explanation_styles=excluded.explanation_styles,
            detail_level=excluded.detail_level,
            updated_at=excluded.updated_at
    """, (background, json.dumps(explanation_styles), detail_level, now, now))
    conn.commit()
    conn.close()


def get_all_topics() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM topics ORDER BY created_at DESC").fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["sources"] = json.loads(d["sources"])
        d["journal"] = json.loads(d["journal"])
        result.append(d)
    return result


def get_topic(topic_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["sources"] = json.loads(d["sources"])
    d["journal"] = json.loads(d["journal"])
    return d


def create_topic(name: str) -> int:
    now = int(time.time() * 1000)
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO topics (name, sources, journal, created_at, updated_at) VALUES (?, '[]', '{}', ?, ?)",
        (name, now, now)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def add_sources(topic_id: int, new_sources: list[dict]):
    topic = get_topic(topic_id)
    if not topic:
        return
    existing = topic["sources"]
    existing.extend(new_sources)
    now = int(time.time() * 1000)
    conn = get_connection()
    conn.execute(
        "UPDATE topics SET sources = ?, updated_at = ? WHERE id = ?",
        (json.dumps(existing), now, topic_id)
    )
    conn.commit()
    conn.close()


def save_journal(topic_id: int, journal: dict):
    now = int(time.time() * 1000)
    conn = get_connection()
    conn.execute(
        "UPDATE topics SET journal = ?, updated_at = ? WHERE id = ?",
        (json.dumps(journal), now, topic_id)
    )
    conn.commit()
    conn.close()


def delete_topic(topic_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
    conn.commit()
    conn.close()
```

- [ ] **Step 2: Run database tests**

```bash
.venv/bin/pytest tests/test_database.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add database.py
git commit -m "feat: replace database layer with profile + topics schema"
```

---

## Task 3: Journal generator

**Files:**
- Create: `journal_generator.py`

- [ ] **Step 1: Create journal_generator.py**

```python
import json
import os
import subprocess


EXPLANATION_STYLE_LABELS = [
    "Use analogies",
    "Show the math",
    "Connect to real examples",
    "Be concise",
    "Give me the intuition first",
]

DETAIL_LEVEL_INSTRUCTIONS = {
    "concise": "Be concise — key points only, no elaboration.",
    "standard": "Provide balanced depth — enough to understand, not exhaustive.",
    "deep": "Be comprehensive — don't skip nuance, edge cases, or derivations.",
}


def build_prompt(topic: str, sources: list[dict], profile: dict | None) -> str:
    sources_text = "\n\n".join(
        f"--- Source: {s['name']} ---\n{s['content']}" for s in sources
    )

    profile_block = ""
    if profile and profile.get("background"):
        styles = ", ".join(profile.get("explanation_styles") or [])
        detail = DETAIL_LEVEL_INSTRUCTIONS.get(profile.get("detail_level", "standard"), "")
        profile_block = f"""
User background: {profile['background']}
Explanation preferences: {styles or "none specified"}
Detail level instruction: {detail}

For the "journal" field: write a personal explanation tailored to this user.
Match their background — skip things they already know well.
Use their preferred explanation style.
"""

    prompt = f"""You are a personal learning journal generator.

Topic: {topic}

Source materials:
{sources_text}

{profile_block}

Return ONLY a JSON object with this exact schema — no markdown fences, no extra text:
{{
  "summary": "3-5 key technical takeaways from the sources",
  "journal": "narrative explanation of this topic written as if explaining it to yourself — technical but clear",
  "concepts": ["key term or concept 1", "key term or concept 2"],
  "resources": [{{"title": "resource title", "type": "Paper|Book|Article|Video|Blog", "description": "one line on why it's useful"}}]
}}
"""
    return prompt


def parse_response(raw: str) -> dict:
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"error": f"Could not parse Claude's response. Raw output: {cleaned[:200]}"}


def generate_journal(topic: str, sources: list[dict], profile: dict | None) -> dict:
    if not sources:
        return {"error": "No sources provided. Add at least one source before generating."}

    prompt = build_prompt(topic, sources, profile)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        result = subprocess.run(
            ["claude", "--print", "--output-format", "text", "--model", "claude-sonnet-4-6", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
    except FileNotFoundError:
        return {"error": "claude CLI not found. Make sure Claude Code is installed and on your PATH."}
    except subprocess.TimeoutExpired:
        return {"error": "Generation timed out after 120 seconds. Try with fewer or shorter sources."}

    if result.returncode != 0:
        return {"error": f"Claude CLI error: {result.stderr.strip()}"}

    return parse_response(result.stdout)
```

- [ ] **Step 2: Run journal generator tests**

```bash
.venv/bin/pytest tests/test_journal_generator.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add journal_generator.py
git commit -m "feat: add journal_generator with Claude CLI subprocess and profile injection"
```

---

## Task 4: Main app — CSS, layout shell, session state

**Files:**
- Replace: `app.py`

- [ ] **Step 1: Replace app.py with shell**

```python
import streamlit as st
import time as time_module
from database import init_db, get_profile, save_profile, get_all_topics, get_topic, create_topic, add_sources, save_journal, delete_topic
from journal_generator import generate_journal, EXPLANATION_STYLE_LABELS

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Learning Journal", page_icon="📖", layout="wide")

# ── Init DB ────────────────────────────────────────────────────────────────────
init_db()

# ── Session state ──────────────────────────────────────────────────────────────
if "active_topic_id" not in st.session_state:
    st.session_state.active_topic_id = None
if "show_profile" not in st.session_state:
    st.session_state.show_profile = False

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
    font-size: 14px;
}
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; max-width: 1100px; }

/* Topic pill tabs */
.topic-pill {
    display: inline-block;
    padding: 5px 14px;
    border-radius: 20px;
    font-size: 12px;
    cursor: pointer;
    background: #f0f0f0;
    color: #888;
    margin-right: 6px;
}
.topic-pill.active { background: #111; color: #fff; }
.topic-pill.new { background: #e8f0fe; color: #3b5bdb; border: 1px dashed #3b5bdb; }

/* Section labels */
.section-label {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 12px;
}
.label-summary { background: #e8f0fe; color: #3b5bdb; }
.label-journal { background: #f3e8fd; color: #7b2d8b; }
.label-concepts { background: #e8fdf0; color: #276138; }
.label-resources { background: #fff3cd; color: #92670a; }

/* Source badge */
.source-badge {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    margin-right: 4px;
}
.badge-pdf { background: #fde8e8; color: #c0392b; }
.badge-txt { background: #e8fdf0; color: #276138; }
.badge-md  { background: #e8f0fe; color: #3b5bdb; }
.badge-doc { background: #fff3cd; color: #92670a; }

/* TOC items */
.toc-item {
    font-size: 12px;
    color: #888;
    padding: 5px 8px;
    border-radius: 6px;
    cursor: pointer;
    border-left: 2px solid transparent;
    margin-bottom: 2px;
}
.toc-item.active {
    color: #111;
    font-weight: 600;
    border-left: 2px solid #111;
    background: #f9f9f9;
}

/* Concept chip */
.chip {
    display: inline-block;
    background: #f5f5f5;
    color: #555;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    margin: 3px 3px 3px 0;
}

/* Resource card */
.resource-card {
    display: flex;
    gap: 10px;
    padding: 10px 12px;
    background: #f9f9f9;
    border-radius: 8px;
    margin-bottom: 6px;
    align-items: flex-start;
}
.resource-title { font-size: 13px; font-weight: 600; margin-bottom: 2px; }
.resource-meta { font-size: 11px; color: #999; }
</style>
""", unsafe_allow_html=True)
```

- [ ] **Step 2: Verify app starts without error**

```bash
.venv/bin/python -c "import app" 2>&1
```

Expected: No output (no import errors).

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: app shell with CSS and session state"
```

---

## Task 5: Profile setup screen

**Files:**
- Modify: `app.py` — append profile UI after the CSS block

- [ ] **Step 1: Add profile setup and settings dialog to app.py**

Append after the CSS block in `app.py`:

```python
# ── Profile setup / settings ───────────────────────────────────────────────────

DETAIL_LEVELS = ["concise", "standard", "deep"]
DETAIL_LABELS = {"concise": "Concise — key points only", "standard": "Standard — balanced depth", "deep": "Deep — don't skip anything"}

@st.dialog("Your Learning Profile")
def profile_dialog():
    st.markdown("This personalizes the Journal section of every entry. Takes 30 seconds.")
    bg = st.text_area(
        "Your background",
        placeholder="e.g. Senior data scientist, strong in Python and stats, weaker in systems and frontend",
        value=get_profile()["background"] if get_profile() else "",
        height=80,
    )
    styles = st.multiselect(
        "How you like things explained",
        options=EXPLANATION_STYLE_LABELS,
        default=get_profile()["explanation_styles"] if get_profile() else [],
    )
    current_level = get_profile()["detail_level"] if get_profile() else "standard"
    level = st.radio(
        "Detail level",
        options=DETAIL_LEVELS,
        format_func=lambda x: DETAIL_LABELS[x],
        index=DETAIL_LEVELS.index(current_level),
        horizontal=True,
    )
    col1, col2 = st.columns([1, 1])
    with col2:
        if st.button("Save Profile", type="primary", use_container_width=True):
            save_profile(bg.strip(), styles, level)
            st.session_state.show_profile = False
            st.rerun()
    with col1:
        if st.button("Cancel", use_container_width=True):
            st.session_state.show_profile = False
            st.rerun()

# Show profile setup on first launch
profile = get_profile()
if profile is None:
    st.markdown("<h2 style='font-size:22px;font-weight:700;margin-bottom:4px'>Welcome to Learning Journal</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color:#999;margin-bottom:24px'>First, tell us a bit about yourself so we can personalize your journals.</p>", unsafe_allow_html=True)
    profile_dialog()
    st.stop()
```

- [ ] **Step 2: Verify first-launch flow renders**

Restart Streamlit, open browser. Should see "Welcome to Learning Journal" with profile dialog.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: profile setup dialog shown on first launch"
```

---

## Task 6: Top nav and topic tabs

**Files:**
- Modify: `app.py` — append nav + tabs after profile block

- [ ] **Step 1: Add nav and topic tabs to app.py**

```python
# ── Top nav ────────────────────────────────────────────────────────────────────
nav_left, nav_right = st.columns([6, 1])
with nav_left:
    st.markdown("<span style='font-weight:700;font-size:17px;letter-spacing:-0.3px'>Learning Journal</span>", unsafe_allow_html=True)
with nav_right:
    if st.button("⚙ Settings", use_container_width=True):
        profile_dialog()

st.divider()

# ── Topic tabs ─────────────────────────────────────────────────────────────────
topics = get_all_topics()

# Set default active topic
if st.session_state.active_topic_id is None and topics:
    st.session_state.active_topic_id = topics[0]["id"]

# Render pill tabs as buttons in a horizontal row
tab_cols = st.columns(min(len(topics) + 1, 8))
for i, topic in enumerate(topics[:7]):
    with tab_cols[i]:
        is_active = topic["id"] == st.session_state.active_topic_id
        label = f"**{topic['name']}**" if is_active else topic["name"]
        if st.button(label, key=f"tab_{topic['id']}", use_container_width=True):
            st.session_state.active_topic_id = topic["id"]
            st.rerun()
with tab_cols[min(len(topics), 7)]:
    if st.button("＋ New Topic", key="new_topic_tab", use_container_width=True):
        new_topic_dialog()
```

- [ ] **Step 2: Add new_topic_dialog stub before the nav block**

Add this function before the nav block:

```python
@st.dialog("New Topic")
def new_topic_dialog():
    name = st.text_input("Topic name", placeholder="e.g. Transformer Architecture")
    uploaded_files = st.file_uploader(
        "Upload sources",
        type=["pdf", "txt", "md", "docx"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    pasted = st.text_area("Or paste text directly", placeholder="Paste a Zoom transcript, article, or notes...", height=120)
    
    # Build source list preview
    sources_preview = []
    if uploaded_files:
        for f in uploaded_files:
            ext = f.name.rsplit(".", 1)[-1].upper()
            sources_preview.append(f"**{ext}** {f.name}")
    if pasted.strip():
        sources_preview.append("**TEXT** Pasted text")

    if sources_preview:
        st.markdown("**Sources queued:**")
        for s in sources_preview:
            st.markdown(f"- {s}")

    has_sources = bool(uploaded_files or pasted.strip())
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Cancel", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Generate Journal", type="primary", use_container_width=True, disabled=not (name.strip() and has_sources)):
            sources = _build_sources(uploaded_files, pasted)
            topic_id = create_topic(name.strip())
            add_sources(topic_id, sources)
            profile = get_profile()
            with st.spinner("Generating your journal…"):
                journal = generate_journal(name.strip(), sources, profile)
            if "error" in journal:
                st.error(journal["error"])
                delete_topic(topic_id)
            else:
                save_journal(topic_id, journal)
                st.session_state.active_topic_id = topic_id
                st.rerun()


def _build_sources(uploaded_files, pasted_text: str) -> list[dict]:
    sources = []
    for f in (uploaded_files or []):
        ext = f.name.rsplit(".", 1)[-1].upper()
        try:
            content = f.read().decode("utf-8", errors="ignore")
        except Exception:
            content = ""
        sources.append({"name": f.name, "type": ext, "content": content})
    if pasted_text.strip():
        sources.append({"name": "pasted_text.txt", "type": "TXT", "content": pasted_text.strip()})
    return sources
```

- [ ] **Step 3: Verify app renders nav + tabs without errors**

Restart Streamlit, complete profile if prompted, verify nav and "+ New Topic" tab appear.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: top nav, topic tabs, and new topic dialog"
```

---

## Task 7: Journal view — TOC + scrollable content

**Files:**
- Modify: `app.py` — append journal view after tabs block

- [ ] **Step 1: Add journal view to app.py**

```python
# ── Journal view ───────────────────────────────────────────────────────────────
st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

if not topics:
    st.markdown("<div style='color:#999;text-align:center;margin-top:80px;font-size:15px'>No topics yet. Click <strong>＋ New Topic</strong> to get started.</div>", unsafe_allow_html=True)
    st.stop()

active_topic = get_topic(st.session_state.active_topic_id) if st.session_state.active_topic_id else None

if not active_topic:
    st.stop()

toc_col, journal_col = st.columns([1, 4])

journal = active_topic.get("journal", {})
has_journal = bool(journal.get("summary"))

with toc_col:
    st.markdown("<div style='font-size:10px;color:#bbb;text-transform:uppercase;font-weight:600;letter-spacing:0.06em;margin-bottom:8px'>Contents</div>", unsafe_allow_html=True)
    if has_journal:
        for section in ["Summary", "Journal", "Key Concepts", "Resources"]:
            st.markdown(f'<div class="toc-item">{section}</div>', unsafe_allow_html=True)

    st.markdown("<div style='margin-top:24px;font-size:10px;color:#bbb;text-transform:uppercase;font-weight:600;letter-spacing:0.06em;margin-bottom:8px'>Sources</div>", unsafe_allow_html=True)
    for source in active_topic.get("sources", []):
        ext = source.get("type", "TXT")
        badge_class = {"PDF": "badge-pdf", "TXT": "badge-txt", "MD": "badge-md"}.get(ext, "badge-doc")
        st.markdown(
            f'<div style="font-size:11px;color:#666;margin-bottom:4px"><span class="source-badge {badge_class}">{ext}</span>{source["name"]}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    if has_journal:
        md_content = _build_markdown(active_topic)
        st.download_button(
            "⬇ Download",
            data=md_content,
            file_name=f"{active_topic['name'].lower().replace(' ', '_')}_journal.md",
            mime="text/markdown",
            use_container_width=True,
        )

    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    if st.button("🗑 Delete Topic", use_container_width=True, key="delete_topic"):
        delete_topic(active_topic["id"])
        st.session_state.active_topic_id = None
        st.rerun()

with journal_col:
    st.markdown(f"<h2 style='font-size:22px;font-weight:700;letter-spacing:-0.5px;margin-bottom:4px'>{active_topic['name']}</h2>", unsafe_allow_html=True)
    source_count = len(active_topic.get("sources", []))
    st.markdown(f"<div style='font-size:12px;color:#999;margin-bottom:24px'>{source_count} source{'s' if source_count != 1 else ''}</div>", unsafe_allow_html=True)

    if not has_journal:
        st.markdown("<div style='color:#999;margin-top:40px'>No journal yet. Add sources and generate.</div>", unsafe_allow_html=True)
        if st.button("＋ Add Sources & Generate", type="primary"):
            new_topic_dialog()
    else:
        # Summary
        st.markdown('<span class="section-label label-summary">Summary</span>', unsafe_allow_html=True)
        st.markdown(f"<p style='color:#333;font-size:13px;line-height:1.7;margin-bottom:32px'>{journal['summary']}</p>", unsafe_allow_html=True)

        # Journal
        st.markdown('<span class="section-label label-journal">Journal</span>', unsafe_allow_html=True)
        st.markdown(f"<p style='color:#333;font-size:13px;line-height:1.7;margin-bottom:32px'>{journal['journal']}</p>", unsafe_allow_html=True)

        # Key Concepts
        st.markdown('<span class="section-label label-concepts">Key Concepts</span>', unsafe_allow_html=True)
        chips = "".join(f'<span class="chip">{c}</span>' for c in journal.get("concepts", []))
        st.markdown(f"<div style='margin-bottom:32px'>{chips}</div>", unsafe_allow_html=True)

        # Resources
        st.markdown('<span class="section-label label-resources">Resources</span>', unsafe_allow_html=True)
        for r in journal.get("resources", []):
            st.markdown(f"""
            <div class="resource-card">
              <div style="font-size:18px">📖</div>
              <div>
                <div class="resource-title">{r.get('title','')}</div>
                <div class="resource-meta">{r.get('type','')} · {r.get('description','')}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # Regenerate
        st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
        if st.button("↺ Add Sources & Regenerate"):
            new_topic_dialog()
```

- [ ] **Step 2: Add _build_markdown helper before the journal view block**

```python
def _build_markdown(topic: dict) -> str:
    import datetime
    j = topic.get("journal", {})
    sources = ", ".join(s["name"] for s in topic.get("sources", []))
    date = datetime.date.today().isoformat()
    lines = [
        f"# {topic['name']}",
        f"Generated: {date}",
        f"Sources: {sources}",
        "",
        "## Summary",
        j.get("summary", ""),
        "",
        "## Journal",
        j.get("journal", ""),
        "",
        "## Key Concepts",
    ]
    for c in j.get("concepts", []):
        lines.append(f"- {c}")
    lines += ["", "## Resources"]
    for r in j.get("resources", []):
        lines.append(f"- **{r.get('title','')}** · {r.get('type','')} — {r.get('description','')}")
    return "\n".join(lines)
```

- [ ] **Step 3: Verify full app flow end-to-end**

Restart Streamlit. Complete these steps manually:
1. Complete profile on first launch
2. Click "+ New Topic", enter a name, paste some text, click Generate
3. Verify journal renders with Summary / Journal / Key Concepts / Resources sections
4. Verify Download button produces a `.md` file
5. Verify Settings gear opens profile editor
6. Verify Delete Topic removes the topic

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: journal view with TOC, content sections, download, and delete"
```

---

## Task 8: Final cleanup

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Update requirements.txt**

```
streamlit>=1.35
python-dotenv
```

(Remove `google-genai` — no longer needed.)

- [ ] **Step 2: Run full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 3: Delete old data directory to start fresh**

```bash
rm -f data/learning.db
```

- [ ] **Step 4: Final commit**

```bash
git add requirements.txt
git commit -m "chore: clean up requirements, remove google-genai dependency"
```
