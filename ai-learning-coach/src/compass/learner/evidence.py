"""Evidence collection for the learner-centered coaching path.

Reduces every source (GitHub repo, doc, blog, reflection) to EvidenceItem
records with a stable id, so the LLM coach can only ever cite evidence that
actually exists — never invent a quote, file path, or evidence id.

Repo evidence reuses the existing deterministic scanner only (not the
per-repo LLM assessor in evidence/llm_assessor.py) — that keeps evidence
collection itself free of a second, separate LLM call; the per-repo LLM
assessment stays exclusive to the old skill_graph path for now.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from ..evidence.scanner import scan_repo
from .models import EvidenceItem, EvidenceSource

DocSourceType = Literal["doc", "blog", "reflection"]


def collect_repo_evidence(repo_path: Path) -> EvidenceSource:
    repo_path = repo_path.resolve()
    scan_result = scan_repo(repo_path)

    items = [
        EvidenceItem(
            source_id=scan_result.repo_name,
            source_type="github_repo",
            summary=f"{ev.skill_id} ({ev.level}): {desc}",
            metadata={"skill_id": ev.skill_id, "level": ev.level},
        )
        for ev in scan_result.evidence
        for desc in (ev.matched_signals or [ev.skill_id])
    ]

    return EvidenceSource(
        source_type="github_repo",
        source_name=scan_result.repo_name,
        items=items,
    )


def collect_doc_evidence(file_path: Path, source_type: DocSourceType) -> EvidenceSource:
    file_path = file_path.resolve()
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    items = [
        EvidenceItem(
            source_id=file_path.name,
            source_type=source_type,
            artifact_path=str(file_path),
            quote=paragraph[:500],
            summary=paragraph[:200],
            metadata={"paragraph_index": i},
        )
        for i, paragraph in enumerate(paragraphs)
    ]

    return EvidenceSource(
        source_type=source_type,
        source_name=file_path.name,
        items=items,
    )
