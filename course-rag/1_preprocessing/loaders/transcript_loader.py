from __future__ import annotations

import re
from pathlib import Path

from langchain_core.documents import Document
from loaders.config import TOPIC_MAP


def _parse_week_session(filename: str) -> tuple[int | None, int | None]:
    match = re.search(r"week\s*(\d+).*?session\s*(\d+)", filename, re.IGNORECASE)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def _parse_vtt(text: str, source_name: str) -> list[Document]:
    """Parse WebVTT Zoom transcript into per-utterance Documents."""
    docs = []
    # Match timestamp lines followed by content
    pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}\s*\n(.*?)(?=\n\n|\Z)",
        re.DOTALL,
    )
    for match in pattern.finditer(text):
        start_time = match.group(1)
        content = match.group(2).strip()

        speaker_match = re.match(r"^([^:\n]+):\s*(.*)", content, re.DOTALL)
        if speaker_match:
            speaker = speaker_match.group(1).strip()
            utterance = speaker_match.group(2).strip()
        else:
            speaker = "unknown"
            utterance = content

        if utterance:
            docs.append(Document(
                page_content=utterance,
                metadata={
                    "source_type": "transcript",
                    "source_name": source_name,
                    "speaker": speaker,
                    "timestamp_start": start_time,
                },
            ))
    return docs


def _parse_bracketed(text: str, source_name: str) -> list[Document]:
    """Parse transcripts with format: [Speaker Name] HH:MM:SS\\nText"""
    docs = []
    pattern = re.compile(r"^\[([^\]]+)\]\s+(\d{1,2}:\d{2}:\d{2})\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, match in enumerate(matches):
        speaker = match.group(1).strip()
        timestamp = match.group(2).strip()
        content_start = match.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        utterance = text[content_start:content_end].strip()
        if utterance:
            docs.append(Document(
                page_content=utterance,
                metadata={
                    "source_type": "transcript",
                    "source_name": source_name,
                    "speaker": speaker,
                    "timestamp_start": timestamp,
                },
            ))
    return docs


def _parse_plain(text: str, source_name: str) -> list[Document]:
    """Parse plain-text Zoom transcript (Speaker HH:MM:SS\\nText)."""
    docs = []
    # Zoom plain-text format: "Speaker Name  HH:MM:SS\nText block\n\n"
    pattern = re.compile(
        r"^(.+?)\s{2,}(\d{1,2}:\d{2}:\d{2})\s*\n(.*?)(?=\n(?:.+?\s{2,}\d{1,2}:\d{2}:\d{2})|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        speaker = match.group(1).strip()
        timestamp = match.group(2).strip()
        utterance = match.group(3).strip()

        if utterance:
            docs.append(Document(
                page_content=utterance,
                metadata={
                    "source_type": "transcript",
                    "source_name": source_name,
                    "speaker": speaker,
                    "timestamp_start": timestamp,
                },
            ))
    return docs


def _merge_short_turns(docs: list[Document], min_chars: int = 120) -> list[Document]:
    """Merge consecutive short utterances from the same speaker into one chunk."""
    if not docs:
        return docs

    merged = []
    current = docs[0]

    for next_doc in docs[1:]:
        same_speaker = current.metadata["speaker"] == next_doc.metadata["speaker"]
        too_short = len(current.page_content) < min_chars

        if same_speaker and too_short:
            current = Document(
                page_content=current.page_content + " " + next_doc.page_content,
                metadata=current.metadata,
            )
        else:
            merged.append(current)
            current = next_doc

    merged.append(current)
    return merged


def load_transcripts(transcript_dir: str | Path) -> list[Document]:
    docs = []
    transcript_dir = Path(transcript_dir)
    files = sorted(transcript_dir.glob("*.vtt")) + sorted(transcript_dir.glob("*.txt"))

    if not files:
        print(f"  No transcripts found in {transcript_dir}")
        return docs

    for path in files:
        print(f"  Loading {path.name}...")
        text = path.read_text(encoding="utf-8")

        if path.suffix == ".vtt" or text.startswith("WEBVTT"):
            raw = _parse_vtt(text, path.name)
        elif re.search(r"^\[[^\]]+\]\s+\d{1,2}:\d{2}:\d{2}", text, re.MULTILINE):
            raw = _parse_bracketed(text, path.name)
        else:
            raw = _parse_plain(text, path.name)
        merged = _merge_short_turns(raw)

        course_week, session = _parse_week_session(path.name)
        topic = TOPIC_MAP.get((course_week, session), "") if course_week else ""
        for doc in merged:
            doc.metadata["course_week"] = course_week
            doc.metadata["session"] = session
            doc.metadata["topic"] = topic

        docs.extend(merged)
        print(f"    → {len(merged)} utterance chunks")

    return docs
