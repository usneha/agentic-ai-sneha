"""Apply evidence records to the skill graph.

Scores are computed from SkillEvidence records via the aggregator, which
produces two independent scores per skill:

  current_score    — penalises inferred/historical evidence
  experience_score — generous on inferred/historical; reflects total exposure

After aggregation, two additive post-processing steps run:
  1. Integration bonuses: +0.10 to both scores when co-dependent skill pairs
     are both evidenced in the same assess pass.
  2. Foundation credits: foundation skill evidence boosts related AI skill
     scores up to a per-pair maximum.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .._data import evidence_signals, skills, skill_domain_map, foundation_credit_map
from .corrections import apply_correction, index_corrections
from ..evidence.aggregator import aggregate_traced
from ..models import LearnerState, ParsedSignal, SkillEvidence, SkillScore


@dataclass
class AssessResult:
    updated_skills: list[str]
    score_deltas: dict[str, float]       # skill_id → current_score change
    confidence_changes: dict[str, str]   # skill_id → new confidence
    integration_bonuses: list[tuple[str, str]]
    breadth_bonuses: list[str]
    aggregation_detail: dict[str, list[dict]] = field(default_factory=dict)  # skill_id → per-record breakdown

    def summary(self) -> str:
        lines = []
        for skill_id in sorted(self.updated_skills):
            delta = self.score_deltas.get(skill_id, 0)
            conf = self.confidence_changes.get(skill_id, "")
            sign = "+" if delta >= 0 else ""
            lines.append(f"  {skill_id:<30}  {sign}{delta:+.3f}  → {conf}")
        return "\n".join(lines)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _confidence_from_score(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _signal_to_evidence(sig: ParsedSignal) -> SkillEvidence:
    """Convert a legacy ParsedSignal (from journal entries) to SkillEvidence."""
    if sig.signal_type == "github_strong":
        etype, conf = "observed", 85
    elif sig.signal_type == "github_moderate":
        etype, conf = "observed", 60
    elif sig.signal_type == "github_weak":
        etype, conf = "inferred", 25
    else:
        etype, conf = "inferred", min(100, int(sig.weight * 100))
    return SkillEvidence(
        skill_id=sig.skill_id,
        evidence_type=etype,
        recency="current",
        confidence=conf,
        source_repo=sig.source,
    )


def _integration_bonus_pairs() -> list[tuple[str, str]]:
    return [
        ("rag.embeddings", "rag.retrieval_basic"),
        ("rag.retrieval_basic", "rag.hybrid"),
        ("rag.retrieval_basic", "rag.reranking"),
        ("eval.datasets", "eval.generation_metrics"),
        ("eval.datasets", "eval.retrieval_metrics"),
        ("agents.tool_use", "agents.single_agent"),
        ("agents.single_agent", "agents.multi_agent"),
        ("memory.conversation", "memory.episodic"),
        ("memory.external", "memory.retrieval"),
        ("deployment.api", "observability.tracing"),
        ("mcp.concepts", "mcp.building"),
    ]


def apply_evidence(state: LearnerState) -> AssessResult:
    """Recompute skill_graph from all evidence in state.evidence plus journal signals.

    Replaces apply_signals. Always recomputes from scratch — integration bonuses
    and foundation credits are re-derived each call and not stored in state.evidence.
    """
    old_scores = {sid: s.current_score for sid, s in state.skill_graph.items()}

    # Collect all evidence: stored records + journal ParsedSignals
    all_evidence: list[SkillEvidence] = list(state.evidence)
    for entry in state.journal_entries:
        for sig in entry.parsed_signals:
            all_evidence.append(_signal_to_evidence(sig))

    # Apply user corrections from `compass review` (accept/downgrade/reject/correct)
    # before grouping. Rejected records are dropped here only — state.evidence and
    # the originating run trace are left untouched for audit.
    corrections_index = index_corrections(state.corrections)
    by_skill: dict[str, list[SkillEvidence]] = {}
    for ev in all_evidence:
        effective = apply_correction(ev, corrections_index)
        if effective is None:
            continue
        by_skill.setdefault(effective.skill_id, []).append(effective)

    aggregation_detail: dict[str, list[dict]] = {}
    for skill_id, records in by_skill.items():
        if skill_id not in state.skill_graph:
            state.skill_graph[skill_id] = SkillScore(skill_id=skill_id)
        ss = state.skill_graph[skill_id]
        current_score, experience_score, breakdown = aggregate_traced(records)
        ss.current_score = current_score
        ss.experience_score = experience_score
        ss.confidence = _confidence_from_score(current_score)
        ss.evidence_sources = sorted({ev.source_repo for ev in records if ev.source_repo})
        ss.last_updated = _now()
        aggregation_detail[skill_id] = breakdown

    # Integration bonuses — additive on top of aggregated scores
    sig_config = evidence_signals()
    integration_bonus: float = sig_config.get("bonuses", {}).get("integration", 0.10)
    evidenced_skills = set(by_skill.keys())
    bonus_pairs: list[tuple[str, str]] = []

    for skill_a, skill_b in _integration_bonus_pairs():
        if skill_a in evidenced_skills and skill_b in evidenced_skills:
            for sid in (skill_a, skill_b):
                if sid in state.skill_graph:
                    ss = state.skill_graph[sid]
                    ss.current_score = min(1.0, ss.current_score + integration_bonus)
                    ss.experience_score = min(1.0, ss.experience_score + integration_bonus)
            bonus_pairs.append((skill_a, skill_b))

    # Foundation credits — recomputed from current foundation skill scores
    credit_map = foundation_credit_map()
    for foundation_id, ai_credits in credit_map.items():
        f_skill = state.skill_graph.get(foundation_id)
        f_score = f_skill.current_score if f_skill else 0.0
        if f_score <= 0:
            continue
        for ai_skill_id, max_boost in ai_credits.items():
            if ai_skill_id in state.skill_graph:
                boost = min(max_boost, f_score * max_boost)
                ss = state.skill_graph[ai_skill_id]
                ss.current_score = min(1.0, ss.current_score + boost)
                ss.experience_score = min(1.0, ss.experience_score + boost)

    # Compute deltas
    score_deltas: dict[str, float] = {}
    updated: list[str] = []
    confidence_changes: dict[str, str] = {}

    for skill_id, ss in state.skill_graph.items():
        delta = ss.current_score - old_scores.get(skill_id, 0.0)
        if abs(delta) > 0.001:
            score_deltas[skill_id] = delta
            updated.append(skill_id)
        if skill_id in by_skill or abs(delta) > 0.001:
            confidence_changes[skill_id] = ss.confidence

    return AssessResult(
        updated_skills=updated,
        score_deltas=score_deltas,
        confidence_changes=confidence_changes,
        integration_bonuses=bonus_pairs,
        breadth_bonuses=[],
        aggregation_detail=aggregation_detail,
    )
