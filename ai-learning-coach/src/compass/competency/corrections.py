"""Apply user corrections (from `compass review`) to evidence before aggregation.

Corrections are persisted decisions about a specific (skill_id, repo) divergence
flag — accept / downgrade / reject / correct. They are applied as a transform
over evidence records at aggregation time in assessor.apply_evidence(); the
underlying evidence ledger and run traces are never mutated, so the original
signal is always recoverable (`compass explain`, `compass trace`).

Keyed by (skill_id, source_repo) rather than evidence_id because SkillEvidence
records for a repo are replaced wholesale on every rescan (new evidence_id each
time) — the correction needs to survive that.
"""
from __future__ import annotations

from ..models import EvidenceCorrection, SkillEvidence

CorrectionKey = tuple[str, str | None]

_DOWNGRADE_FACTOR = 0.5


def index_corrections(corrections: list[EvidenceCorrection]) -> dict[CorrectionKey, EvidenceCorrection]:
    """Build a lookup keyed by (skill_id, source_repo). Latest correction wins."""
    index: dict[CorrectionKey, EvidenceCorrection] = {}
    for c in sorted(corrections, key=lambda c: c.created_at):
        index[(c.skill_id, c.source_repo)] = c
    return index


def find_correction(
    skill_id: str,
    source_repo: str | None,
    index: dict[CorrectionKey, EvidenceCorrection],
) -> EvidenceCorrection | None:
    """A repo-specific correction takes priority over one that applies everywhere."""
    return index.get((skill_id, source_repo)) or index.get((skill_id, None))


def apply_correction(
    record: SkillEvidence,
    index: dict[CorrectionKey, EvidenceCorrection],
) -> SkillEvidence | None:
    """Return the effective evidence record after applying any matching correction.

    Returns None if the record should be excluded from scoring (rejected) —
    the caller is responsible for dropping it from the aggregation input while
    leaving the original record untouched in state.evidence.

    Corrections only ever apply to LLM-sourced evidence (record.source == "llm")
    — they originate from `compass review` of LLM divergence flags and must
    never touch deterministic scanner evidence for the same skill/repo.
    """
    if record.source != "llm":
        return record
    correction = find_correction(record.skill_id, record.source_repo, index)
    if correction is None or correction.action == "accept":
        return record
    if correction.action == "reject":
        return None
    if correction.action == "downgrade":
        return record.model_copy(update={
            "confidence": max(1, round(record.confidence * _DOWNGRADE_FACTOR)),
        })
    if correction.action == "correct":
        updates: dict = {}
        if correction.corrected_skill_id:
            updates["skill_id"] = correction.corrected_skill_id
        if correction.corrected_recency:
            updates["recency"] = correction.corrected_recency
        if correction.corrected_evidence_type:
            updates["evidence_type"] = correction.corrected_evidence_type
        return record.model_copy(update=updates) if updates else record
    return record
