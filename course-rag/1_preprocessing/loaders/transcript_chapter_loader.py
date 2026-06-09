"""
Loads raw transcripts segmented by chapter using transcript-chapters-metadata.

Each Document covers one chapter and has content:

    Chapter: <chapter_title>

    Speaker Name: utterance text
    Speaker Name: utterance text
    ...

This makes the chapter title part of the embedding's semantic signal.
"""

import bisect
import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

from langchain_core.documents import Document

TRANSCRIPTS_DIR = Path(__file__).parent.parent.parent / "data" / "transcripts"
CHAPTERS_FILE = TRANSCRIPTS_DIR / "transcript-chapters-metadata"

# Maps video_title in metadata → (raw_filename, course_week, session_num)
SESSION_MAP = {
    "Live Session 1- Week 1": ("session1-week1-lecture-raw-transcript.md", 1, 1),
    "Live Session 2 - Week 1": ("session2-week1-lecture-raw-transcript.md", 1, 2),
    "Live Session 1- Week 2": ("session1-week2-lecture-raw-transcript", 2, 1),
    "Live Session 2 - Week 2": ("session2-week2-lecture-raw-transcript", 2, 2),
}

_TS_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")


def _ts_to_seconds(ts: str) -> int:
    h, m, s = ts.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def _is_speaker_name(line: str) -> bool:
    """Heuristic: title-cased words only, no sentence punctuation, ≤5 words."""
    words = line.strip().split()
    if not words or len(words) > 5:
        return False
    return all(re.match(r"^[A-Z][a-zA-Z\-']*$", w) for w in words)


def _parse_utterances(path: Path) -> List[Tuple[str, str, int]]:
    """Returns list of (speaker, text, timestamp_seconds)."""
    utterances = []
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines()]

    current_speaker = "Unknown"
    text_acc: List[str] = []
    after_timestamp = True  # treat file start same as post-timestamp

    for line in lines:
        if not line:
            continue

        if _TS_RE.match(line):
            text = " ".join(text_acc).strip()
            if text:
                utterances.append((current_speaker, text, _ts_to_seconds(line)))
            text_acc = []
            after_timestamp = True
        elif after_timestamp and _is_speaker_name(line):
            current_speaker = line
            after_timestamp = False
        else:
            text_acc.append(line)
            after_timestamp = False

    return utterances


def _build_chapter_docs(
    utterances: List[Tuple[str, str, int]],
    chapters: List[dict],
    session_title: str,
    course_week: int,
    session_num: int,
    source_name: str,
) -> List[Document]:
    if not utterances or not chapters:
        return []

    starts = [c["start_seconds"] for c in chapters]
    # Group utterances by chapter index
    groups: dict[int, List[Tuple[str, str, int]]] = {i: [] for i in range(len(chapters))}
    for speaker, text, ts in utterances:
        idx = bisect.bisect_right(starts, ts) - 1
        idx = max(idx, 0)
        groups[idx].append((speaker, text, ts))

    docs = []
    for i, chapter in enumerate(chapters):
        chapter_utterances = groups[i]
        if not chapter_utterances:
            continue

        # Build content with chapter title as semantic signal
        lines = [f"Chapter: {chapter['title']}", ""]
        prev_speaker = None
        for speaker, text, _ in chapter_utterances:
            if speaker != prev_speaker:
                lines.append(f"{speaker}: {text}")
                prev_speaker = speaker
            else:
                lines.append(text)

        end_seconds = (
            chapters[i + 1]["start_seconds"] - 1
            if i + 1 < len(chapters)
            else chapter_utterances[-1][2]
        )

        docs.append(Document(
            page_content="\n".join(lines),
            metadata={
                "source_type": "transcript_chapter",
                "source_name": source_name,
                "chapter_title": chapter["title"],
                "session_title": session_title,
                "course_week": course_week,
                "session": session_num,
                "timestamp_start": chapter["start_seconds"],
                "timestamp_end": end_seconds,
            },
        ))

    return docs


def load_transcript_chapters() -> List[Document]:
    """Load all sessions from raw transcripts, segmented by chapter."""
    all_docs = []

    for line in CHAPTERS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip().rstrip(";")
        if not line:
            continue

        # The file has malformed JSON: chapters array missing closing `]`.
        # `...8413}}` should be `...8413]}` — fix before parsing.
        if line.endswith("}}"):
            line = line[:-1] + "]}"

        data = json.loads(line)
        session_title = data["analytics_metadata"]["video_title"]
        chapters = sorted(data["chapters"], key=lambda c: c["start_seconds"])

        if session_title not in SESSION_MAP:
            print(f"   ⚠️  No file mapping for '{session_title}', skipping")
            continue

        filename, course_week, session_num = SESSION_MAP[session_title]
        raw_path = TRANSCRIPTS_DIR / filename

        if not raw_path.exists():
            print(f"   ⚠️  Missing file: {filename}, skipping")
            continue

        utterances = _parse_utterances(raw_path)
        docs = _build_chapter_docs(
            utterances, chapters, session_title, course_week, session_num, filename
        )
        all_docs.extend(docs)
        print(f"   {filename}: {len(docs)} chapters")

    return all_docs
