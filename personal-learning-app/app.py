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

# ── Profile setup / settings ───────────────────────────────────────────────────

DETAIL_LEVELS = ["concise", "standard", "deep"]
DETAIL_LABELS = {"concise": "Concise — key points only", "standard": "Standard — balanced depth", "deep": "Deep — don't skip anything"}

@st.dialog("Your Learning Profile")
def profile_dialog():
    st.markdown("This personalizes the Journal section of every entry. Takes 30 seconds.")
    _existing = get_profile()
    bg = st.text_area(
        "Your background",
        placeholder="e.g. Senior data scientist, strong in Python and stats, weaker in systems and frontend",
        value=_existing["background"] if _existing else "",
        height=80,
    )
    styles = st.multiselect(
        "How you like things explained",
        options=EXPLANATION_STYLE_LABELS,
        default=_existing["explanation_styles"] if _existing else [],
    )
    current_level = _existing["detail_level"] if _existing else "standard"
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

# Show profile setup on first launch (inline form, not dialog — dialogs require a button click to open)
profile = get_profile()
if profile is None:
    st.markdown("<h2 style='font-size:22px;font-weight:700;margin-bottom:4px'>Welcome to Learning Journal</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color:#999;margin-bottom:24px'>Tell us a bit about yourself so we can personalize your journals.</p>", unsafe_allow_html=True)
    with st.form("first_launch_profile"):
        bg = st.text_area(
            "Your background",
            placeholder="e.g. Senior data scientist, strong in Python and stats, weaker in systems and frontend",
            height=80,
        )
        styles = st.multiselect("How you like things explained", options=EXPLANATION_STYLE_LABELS)
        level = st.radio(
            "Detail level",
            options=DETAIL_LEVELS,
            format_func=lambda x: DETAIL_LABELS[x],
            index=1,
            horizontal=True,
        )
        if st.form_submit_button("Save Profile & Continue", type="primary", use_container_width=True):
            save_profile(bg.strip(), styles, level)
            st.rerun()
    st.stop()

# ── Helper: build sources list from uploads + pasted text ──────────────────────
def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        import pypdf, io
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        return f"[Could not extract PDF text: {e}]"


def _build_sources(uploaded_files, pasted_text: str) -> list[dict]:
    sources = []
    for f in (uploaded_files or []):
        ext = f.name.rsplit(".", 1)[-1].upper()
        raw = f.read()
        if ext == "PDF":
            content = _extract_pdf_text(raw)
        else:
            content = raw.decode("utf-8", errors="ignore")
        sources.append({"name": f.name, "type": ext, "content": content})
    if pasted_text.strip():
        sources.append({"name": "pasted_text.txt", "type": "TXT", "content": pasted_text.strip()})
    return sources


# ── New Topic dialog ───────────────────────────────────────────────────────────
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


# ── Top nav ────────────────────────────────────────────────────────────────────
topics = get_all_topics()

if st.session_state.active_topic_id is None and topics:
    st.session_state.active_topic_id = topics[0]["id"]

# ── Empty state ────────────────────────────────────────────────────────────────
if not topics:
    st.markdown("""
    <style>
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        background: #0c0c0c !important;
    }
    [data-testid="stHeader"] { display: none !important; }
    .block-container { padding-top: 0 !important; max-width: 100% !important; }

    /* Dark page background with grid */
    [data-testid="stMain"] {
        background-image:
            linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px) !important;
        background-size: 44px 44px !important;
    }

    /* Tag pill */
    .l-tag {
        display: inline-flex; align-items: center; gap: 8px;
        background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
        color: rgba(255,255,255,0.5); font-size: 12px;
        padding: 5px 13px; border-radius: 6px; margin-bottom: 16px;
    }
    .l-dot { width:7px;height:7px;border-radius:50%;background:#4ade80;display:inline-block; }
    .l-h1 { font-size: 52px !important; font-weight: 800 !important; line-height: 1.05 !important;
        letter-spacing: -2px !important; color: #fff !important; margin-bottom: 16px !important; }
    .l-h1 em { font-style: normal; color: #a78bfa; }
    .l-sub { font-size: 15px; color: rgba(255,255,255,0.42); line-height: 1.75; margin-bottom: 0; }

    /* CTA button */
    [data-testid="stButton-landing_cta"] button {
        background: #fff !important; color: #0c0c0c !important;
        font-size: 15px !important; font-weight: 700 !important;
        padding: 13px 28px !important; border-radius: 10px !important;
        border: none !important; width: auto !important;
    }
    [data-testid="stButton-landing_cta"] button:hover { background: #e2e2e2 !important; }

    /* Preview card */
    .l-card {
        background: #141414; border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px; padding: 28px;
    }
    .l-card-title { font-size: 13px; font-weight: 700; color: #fff; margin-bottom: 20px;
        display: flex; align-items: center; gap: 8px; }
    .l-eg { font-size: 11px; color: rgba(255,255,255,0.3);
        background: rgba(255,255,255,0.06); padding: 2px 8px; border-radius: 4px; }
    .l-row { display: flex; align-items: flex-start; gap: 12px;
        padding: 11px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
    .l-row:last-child { border-bottom: none; }
    .l-pill { font-size: 10px; font-weight: 700; padding: 3px 9px; border-radius: 5px;
        flex-shrink: 0; margin-top: 2px; white-space: nowrap; }
    .lp-b{background:rgba(59,91,219,0.25);color:#818cf8;}
    .lp-p{background:rgba(167,139,250,0.18);color:#c084fc;}
    .lp-g{background:rgba(74,222,128,0.14);color:#4ade80;}
    .lp-a{background:rgba(251,191,36,0.14);color:#fbbf24;}
    .l-row-text { font-size: 12px; color: rgba(255,255,255,0.4); line-height: 1.55; }
    </style>
    """, unsafe_allow_html=True)

    # Nav
    nav_l, nav_r = st.columns([6, 1])
    with nav_l:
        st.markdown("<div style='padding:20px 0 16px;font-size:15px;font-weight:700;color:#fff;letter-spacing:-0.3px'>📖 Learning Journal</div>", unsafe_allow_html=True)
    with nav_r:
        st.markdown("<div style='padding:20px 0 16px'></div>", unsafe_allow_html=True)
        if st.button("⚙ Settings", key="landing_settings"):
            profile_dialog()
    st.markdown("<hr style='border:none;border-top:1px solid rgba(255,255,255,0.07);margin:0 0 0 0'>", unsafe_allow_html=True)

    # Hero
    left_col, right_col = st.columns([1, 1], gap="large")
    with left_col:
        st.markdown("""
        <div style='padding: 60px 0 24px'>
          <div class='l-tag'><span class='l-dot'></span>AI-powered · Personalized to you</div>
          <div class='l-h1'>Your materials.<br>Your <em>journal</em>.</div>
          <p class='l-sub'>Drop in PDFs, Zoom transcripts, lecture notes, or raw text.
          Get a structured journal written for your background —
          summary, explanation, key concepts, resources. One click to download.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("＋  New Topic", key="landing_cta"):
            new_topic_dialog()

    with right_col:
        st.markdown("""
        <div style='padding: 60px 0 24px'>
        <div class='l-card'>
          <div class='l-card-title'>📖 Transformer Architecture <span class='l-eg'>example</span></div>
          <div class='l-row'><span class='l-pill lp-b'>Summary</span><span class='l-row-text'>3–5 key takeaways from your sources</span></div>
          <div class='l-row'><span class='l-pill lp-p'>Journal</span><span class='l-row-text'>Personal explanation written for your background</span></div>
          <div class='l-row'><span class='l-pill lp-g'>Concepts</span><span class='l-row-text'>Self-attention · Positional encoding · Multi-head</span></div>
          <div class='l-row'><span class='l-pill lp-a'>Resources</span><span class='l-row-text'>Papers, videos &amp; blogs curated from your sources</span></div>
        </div>
        </div>
        """, unsafe_allow_html=True)

    st.stop()

# ── Top nav (only shown when topics exist) ─────────────────────────────────────
nav_left, nav_right = st.columns([6, 1])
with nav_left:
    st.markdown("<span style='font-weight:700;font-size:17px;letter-spacing:-0.3px'>Learning Journal</span>", unsafe_allow_html=True)
with nav_right:
    if st.button("⚙ Settings", use_container_width=True):
        profile_dialog()

st.divider()

# ── Topic tabs ─────────────────────────────────────────────────────────────────
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

# ── Journal view ───────────────────────────────────────────────────────────────
st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

active_topic = get_topic(st.session_state.active_topic_id) if st.session_state.active_topic_id else None

if not active_topic:
    st.stop()

toc_col, journal_col = st.columns([1, 4])

journal = active_topic.get("journal", {})
has_journal = bool(journal.get("summary"))


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
            file_name=f"{__import__('re').sub(r'[^\w\s-]', '', active_topic['name']).strip().lower().replace(' ', '_')}_journal.md",
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
        st.markdown('<span class="section-label label-summary">Summary</span>', unsafe_allow_html=True)
        st.markdown(f"<p style='color:#333;font-size:13px;line-height:1.7;margin-bottom:32px'>{journal['summary']}</p>", unsafe_allow_html=True)

        st.markdown('<span class="section-label label-journal">Journal</span>', unsafe_allow_html=True)
        st.markdown(f"<p style='color:#333;font-size:13px;line-height:1.7;margin-bottom:32px'>{journal['journal']}</p>", unsafe_allow_html=True)

        st.markdown('<span class="section-label label-concepts">Key Concepts</span>', unsafe_allow_html=True)
        chips = "".join(f'<span class="chip">{c}</span>' for c in journal.get("concepts", []))
        st.markdown(f"<div style='margin-bottom:32px'>{chips}</div>", unsafe_allow_html=True)

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

        st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
        if st.button("↺ Add Sources & Regenerate"):
            new_topic_dialog()
