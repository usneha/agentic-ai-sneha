"""
Streamlit chat UI for the "Mastering Agentic AI" course assistant.

Run:
    uv run streamlit run 5_chat/app.py
"""

import os
import sys
from pathlib import Path

# Must be set before chromadb is imported (transitively, via generator)
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from generator import generate

st.set_page_config(page_title="Mastering Agentic AI — Course Assistant", page_icon="🤖")
st.title("Mastering Agentic AI — Course Assistant")


def _source_label(doc):
    meta = doc.metadata
    label = meta.get("source_name", "unknown")
    if "page" in meta:
        label += f" p.{meta['page']}"
    if "speaker" in meta:
        label += f" — {meta['speaker']}"
    return label


def _render_sources(results):
    with st.expander("Sources"):
        for i, (doc, _origin, _rerank_score, _sem_score) in enumerate(results, 1):
            st.markdown(f"**[Source {i}]** {_source_label(doc)}")
            preview = " ".join(doc.page_content.split())[:300]
            st.caption(f"{preview}...")


if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            _render_sources(message["sources"])

if prompt := st.chat_input("Ask a question about the course..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer, results = generate(prompt)
        st.markdown(answer)
        if results:
            _render_sources(results)

    st.session_state.messages.append({"role": "assistant", "content": answer, "sources": results})
