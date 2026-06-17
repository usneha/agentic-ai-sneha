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
    if not records:
        return 0.0, 0.0

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

    return _combine(current_contribs), _combine(experience_contribs)
