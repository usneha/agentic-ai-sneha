"""Evidence aggregator — produces current_score and experience_score from evidence records.

current_score  — penalises inferred/historical; reflects active, demonstrated capability.
experience_score — generous on inferred/historical; reflects total breadth of exposure.

Combination rule: best contribution wins; each additional corroborating record adds a
diminishing 10% bonus, capped at 1.0.
"""
from __future__ import annotations

from ..models import SkillEvidence

_CURRENT_TYPE_WEIGHT    = {"observed": 1.0, "inferred": 0.5, "synthesized": 0.3}
_CURRENT_RECENCY_WEIGHT = {"current": 1.0, "unknown": 0.70, "historical": 0.5}

_EXPERIENCE_TYPE_WEIGHT    = {"observed": 1.0, "inferred": 0.7, "synthesized": 0.4}
_EXPERIENCE_RECENCY_WEIGHT = {"current": 1.0, "unknown": 0.95, "historical": 0.9}


def _combine(contribs: list[float]) -> float:
    ranked = sorted(contribs, reverse=True)
    score = ranked[0]
    for extra in ranked[1:]:
        score += extra * 0.1
    return min(1.0, score)


def aggregate(records: list[SkillEvidence]) -> tuple[float, float]:
    """Return (current_score, experience_score) for a list of evidence records."""
    current_score, experience_score, _breakdown = aggregate_traced(records)
    return current_score, experience_score


def aggregate_traced(records: list[SkillEvidence]) -> tuple[float, float, list[dict]]:
    """Same as aggregate(), but also returns a per-record contribution breakdown.

    Each breakdown entry shows the inputs and resulting contribution for one
    evidence record, before the diminishing-bonus combination step. Used by
    apply_evidence() to populate AssessResult.aggregation_detail for tracing —
    does not change the scoring formula itself.
    """
    if not records:
        return 0.0, 0.0, []

    current_contribs = [
        (r.confidence / 100)
        * _CURRENT_TYPE_WEIGHT[r.evidence_type]
        * _CURRENT_RECENCY_WEIGHT[r.recency]
        for r in records
    ]
    experience_contribs = [
        (r.confidence / 100)
        * _EXPERIENCE_TYPE_WEIGHT[r.evidence_type]
        * _EXPERIENCE_RECENCY_WEIGHT[r.recency]
        for r in records
    ]

    breakdown = [
        {
            "source_repo": r.source_repo,
            "evidence_type": r.evidence_type,
            "recency": r.recency,
            "confidence": r.confidence,
            "current_contribution": round(cc, 4),
            "experience_contribution": round(ec, 4),
        }
        for r, cc, ec in zip(records, current_contribs, experience_contribs)
    ]

    return _combine(current_contribs), _combine(experience_contribs), breakdown
