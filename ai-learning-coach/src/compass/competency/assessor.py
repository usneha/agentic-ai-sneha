"""Apply evidence signals to the skill graph.

Implements scoring, confidence calculation, breadth/integration bonuses,
and prerequisite awareness. All deterministic — no LLM calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .._data import evidence_signals, skills, skill_domain_map, foundation_credit_map
from ..models import LearnerState, ParsedSignal, SkillScore


@dataclass
class AssessResult:
    updated_skills: list[str]
    score_deltas: dict[str, float]       # skill_id → score change
    confidence_changes: dict[str, str]   # skill_id → new confidence
    integration_bonuses: list[tuple[str, str]]  # pairs that got +0.10
    breadth_bonuses: list[str]           # skills that got +0.15 (future: multi-repo)

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


def _compute_confidence(signals: list[ParsedSignal]) -> str:
    """Derive confidence level from the set of signals for one skill."""
    types = {s.signal_type for s in signals}
    repos = {s.source for s in signals}

    if len(repos) > 1:
        return "high"
    if "github_strong" in types and len(types) > 1:
        return "high"
    if "github_strong" in types:
        return "medium"
    if "github_moderate" in types:
        return "medium"
    # journal-only or weak-only → low
    return "low"


def _integration_bonus_pairs() -> list[tuple[str, str]]:
    """Return co-dependent skill pairs eligible for the integration bonus."""
    # Pairs from skills.yaml where skills share prerequisites (tight coupling)
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


def apply_signals(state: LearnerState, signals: list[ParsedSignal]) -> AssessResult:
    """Apply a list of ParsedSignal objects to the learner's skill graph.

    Modifies state.skill_graph in place. Returns a summary of changes.
    """
    sig_config = evidence_signals()
    source_weights: dict[str, float] = sig_config["source_weights"]
    bonus_config = sig_config.get("bonuses", {})
    integration_bonus: float = bonus_config.get("integration", 0.10)

    # Group signals by skill_id
    by_skill: dict[str, list[ParsedSignal]] = {}
    for sig in signals:
        by_skill.setdefault(sig.skill_id, []).append(sig)

    score_deltas: dict[str, float] = {}
    confidence_changes: dict[str, str] = {}
    updated: list[str] = []

    for skill_id, sigs in by_skill.items():
        current = state.skill_graph.get(skill_id)
        if current is None:
            current = SkillScore(skill_id=skill_id)
            state.skill_graph[skill_id] = current

        old_score = current.score
        delta = 0.0

        # Each (skill, signal_type) pair counts once — deduplicate
        seen_types: set[str] = set()
        for sig in sigs:
            if sig.signal_type in seen_types:
                continue
            seen_types.add(sig.signal_type)
            weight = source_weights.get(sig.signal_type, sig.weight)
            delta += weight

        # Cap at 1.0
        new_score = min(1.0, old_score + delta)
        new_conf = _compute_confidence(sigs)

        # Accumulate evidence sources (unique)
        existing_sources = set(current.evidence_sources)
        new_sources = {s.source for s in sigs}
        combined_sources = sorted(existing_sources | new_sources)

        current.score = new_score
        current.confidence = new_conf
        current.evidence_sources = combined_sources
        current.last_updated = _now()

        if abs(new_score - old_score) > 0.001:
            score_deltas[skill_id] = new_score - old_score
            updated.append(skill_id)
        confidence_changes[skill_id] = new_conf

    # Integration bonuses — if both skills in a pair got signals in this scan
    found_skills = set(by_skill.keys())
    bonus_pairs: list[tuple[str, str]] = []
    for skill_a, skill_b in _integration_bonus_pairs():
        if skill_a in found_skills and skill_b in found_skills:
            for skill_id in (skill_a, skill_b):
                if skill_id in state.skill_graph:
                    state.skill_graph[skill_id].score = min(
                        1.0, state.skill_graph[skill_id].score + integration_bonus
                    )
                    score_deltas[skill_id] = score_deltas.get(skill_id, 0) + integration_bonus
                    if skill_id not in updated:
                        updated.append(skill_id)
            bonus_pairs.append((skill_a, skill_b))

    # Recompute foundation credits — always reset then recalculate from current state
    # so repeated assess calls don't accumulate credits.
    for s in state.skill_graph.values():
        s.foundation_score = 0.0
    credit_map = foundation_credit_map()
    for foundation_id, ai_credits in credit_map.items():
        f_skill = state.skill_graph.get(foundation_id)
        f_score = f_skill.score if f_skill else 0.0
        if f_score <= 0:
            continue
        for ai_skill_id, max_boost in ai_credits.items():
            if ai_skill_id in state.skill_graph:
                state.skill_graph[ai_skill_id].foundation_score = min(
                    max_boost,
                    state.skill_graph[ai_skill_id].foundation_score + f_score * max_boost,
                )

    return AssessResult(
        updated_skills=updated,
        score_deltas=score_deltas,
        confidence_changes=confidence_changes,
        integration_bonuses=bonus_pairs,
        breadth_bonuses=[],
    )
