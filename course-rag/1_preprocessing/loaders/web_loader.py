from __future__ import annotations

import re
import tempfile
import urllib.request
from pathlib import Path

import yaml
from langchain_core.documents import Document
from langchain_community.document_loaders import PDFPlumberLoader

try:
    import trafilatura
    _USE_TRAFILATURA = True
except ImportError:
    _USE_TRAFILATURA = False
    from langchain_community.document_loaders import WebBaseLoader


def _is_pdf_url(url: str) -> bool:
    from urllib.parse import urlparse
    path = urlparse(url).path
    return path.endswith(".pdf") or "/pdf/" in path


def _fetch_pdf_url(url: str, metadata: dict) -> list[Document]:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        urllib.request.urlretrieve(url, tmp.name)
        loader = PDFPlumberLoader(tmp.name)
        pages = loader.load()
        for page in pages:
            page.metadata.update({**metadata, "source_type": "pdf"})
        return pages


def _fetch_html(url: str) -> str | None:
    if _USE_TRAFILATURA:
        downloaded = trafilatura.fetch_url(url)
        return trafilatura.extract(downloaded, favor_precision=True, include_tables=False, include_comments=False) if downloaded else None
    loader = WebBaseLoader(url)
    pages = loader.load()
    return pages[0].page_content if pages else None


def _parse_readings(yaml_path: Path) -> list[dict]:
    """Extract active readings from course_structure.yaml as list of dicts with url + metadata."""
    structure = yaml.safe_load(yaml_path.read_text())
    readings = []
    for week_num, week_data in structure.get("weeks", {}).items():
        week_title = week_data.get("title", "")
        for entry in (week_data.get("readings") or []):
            if not isinstance(entry, str):
                continue
            url_match = re.search(r"https?://\S+", entry)
            if not url_match:
                continue
            url = url_match.group(0)
            title = entry[:url_match.start()].rstrip(": ").strip() or url
            readings.append({
                "url": url,
                "source_name": title,
                "course_week": int(week_num),
                "session": None,
                "topic": week_title,
            })
    return readings


def load_from_course_structure(yaml_path: str | Path) -> tuple[list[Document], list[str]]:
    docs: list[Document] = []
    failed: list[str] = []
    yaml_path = Path(yaml_path)

    if not yaml_path.exists():
        print(f"  course_structure.yaml not found: {yaml_path}")
        return docs, failed

    readings = _parse_readings(yaml_path)
    if not readings:
        print("  No active readings found in course_structure.yaml")
        return docs, failed

    for r in readings:
        url = r["url"]
        print(f"  Fetching {url}...")
        base_meta = {
            "source_type": "web",
            "source_name": r["source_name"],
            "url": url,
            "course_week": r["course_week"],
            "session": r["session"],
            "topic": r["topic"],
        }
        if _is_pdf_url(url):
            pages = _fetch_pdf_url(url, base_meta)
            docs.extend(pages)
            print(f"    → PDF: {len(pages)} pages")
        else:
            content = _fetch_html(url)
            if content:
                docs.append(Document(page_content=content, metadata=base_meta))
                print(f"    → {len(content):,} chars")
            else:
                print(f"    → failed to extract content")
                failed.append(url)

    return docs, failed
