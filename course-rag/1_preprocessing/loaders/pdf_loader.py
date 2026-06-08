from __future__ import annotations

import logging
import re
from pathlib import Path

from langchain_community.document_loaders import PDFPlumberLoader
from langchain_core.documents import Document

logging.getLogger("pdfplumber").setLevel(logging.ERROR)

from loaders.config import TOPIC_MAP


def _parse_week_session(filename: str) -> tuple[int | None, int | None]:
    match = re.search(r"[Ww]eek\s*(\d+).*?[Ss]ession\s*(\d+)", filename)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def load_pdfs(pdf_dir: str | Path) -> list[Document]:
    docs = []
    pdf_dir = Path(pdf_dir)
    pdf_files = sorted(pdf_dir.glob("**/*.pdf"))

    if not pdf_files:
        print(f"  No PDFs found in {pdf_dir}")
        return docs

    for pdf_path in pdf_files:
        print(f"  Loading {pdf_path.name}...")
        loader = PDFPlumberLoader(str(pdf_path))
        pages = loader.load()

        course_week, session = _parse_week_session(pdf_path.name)
        topic = TOPIC_MAP.get((course_week, session), "") if course_week else ""
        raw_title = pages[0].metadata.get("Title", "") if pages else ""
        author = pages[0].metadata.get("Author", "") if pages else ""

        for page in pages:
            page.metadata = {
                "source_type": "pdf",
                "source_name": pdf_path.name,
                "page": page.metadata.get("page", 0),
                "total_pages": page.metadata.get("total_pages", len(pages)),
                "title": raw_title,
                "author": author,
                "course_week": course_week,
                "session": session,
                "topic": topic,
            }
        docs.extend(pages)
        print(f"    → {len(pages)} pages")

    return docs
