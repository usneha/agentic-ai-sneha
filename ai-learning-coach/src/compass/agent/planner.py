"""Deterministic planner — 5-step algorithm from PLANNER_DESIGN.md.

No LLM calls. All scoring, filtering, and ranking is done by rule.
The agent layer uses this output to generate user-facing rationale.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .. import _data
from ..models import LearnerState


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class VelocityResult:
    tier: str           # high | moderate | low | stalled
    signal: str         # high_accel | high_stable | moderate | low_recover | low_decel | stalled
    multiplier: float   # velocity_mult for gap priority
    re_engagement_mode: bool = False
    burst_pattern: bool = False
    score_7d: float = 0.0
    score_14d: float = 0.0


@dataclass
class MilestoneCandidate:
    domain: str
    domain_name: str
    priority: float
    target_skills: list[str]
    skill_priorities: dict[str, float] = field(default_factory=dict)
    skill_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class PlanResult:
    top: MilestoneCandidate | None
    horizon: list[MilestoneCandidate]
    velocity: VelocityResult
    re_engagement_mode: bool = False
    no_eligible_skills: bool = False
    eligible_skill_count: int = 0


# ── Velocity ──────────────────────────────────────────────────────────────────

def compute_velocity(state: LearnerState) -> VelocityResult:
    """Derive velocity tier from timestamped evidence in the learner state."""
    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)
    cutoff_14d = now - timedelta(days=14)

    def ts_utc(dt: datetime) -> datetime:
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    score_7d = 0.0
    score_14d = 0.0

    # Skill updates (weight 1.0 each)
    for s in state.skill_graph.values():
        if s.current_score > 0 and s.evidence_sources and s.evidence_sources != ["role_prior"]:
            ts = ts_utc(s.last_updated)
            if ts >= cutoff_7d:
                score_7d += 1.0
            elif ts >= cutoff_14d:
                score_14d += 1.0

    # Journal entries (weight 0.5)
    for entry in state.journal_entries:
        ts = ts_utc(entry.date)
        if ts >= cutoff_7d:
            score_7d += 0.5
        elif ts >= cutoff_14d:
            score_14d += 0.5

    # Milestone transitions (weight 2.0)
    for m in state.completed_milestones:
        if m.completed_at:
            ts = ts_utc(m.completed_at)
            if ts >= cutoff_7d:
                score_7d += 2.0
            elif ts >= cutoff_14d:
                score_14d += 2.0

    total_14d = score_7d + score_14d

    if score_7d >= 2.0 and total_14d >= 3.0:
        tier = "high"
        signal = "high_stable"
        mult = 1.10
    elif score_7d >= 0.5 or total_14d >= 1.0:
        tier = "moderate"
        signal = "moderate"
        mult = 1.00
    elif score_7d > 0 or total_14d >= 0.5:
        tier = "low"
        signal = "low_recover"
        mult = 0.95
    else:
        tier = "stalled"
        signal = "stalled"
        mult = 0.0

    return VelocityResult(
        tier=tier,
        signal=signal,
        multiplier=mult,
        re_engagement_mode=(tier == "stalled"),
        score_7d=score_7d,
        score_14d=total_14d,
    )


# ── Eligibility helpers ───────────────────────────────────────────────────────

def _prereqs_met(meta: dict, skill_graph: dict, velocity_tier: str) -> bool:
    threshold_adj = {"high": -0.05, "moderate": 0.0, "low": +0.05, "stalled": +0.10}
    prereqs = meta.get("prerequisites", [])
    base_thresh = meta.get("min_prerequisite_score", 0.30)
    thresh = max(0.0, base_thresh + threshold_adj.get(velocity_tier, 0.0))

    for prereq_id in prereqs:
        s = skill_graph.get(prereq_id)
        if s is None or s.effective_score < thresh:
            return False
    return True


def _activation_gate_met(meta: dict, skill_graph: dict) -> bool:
    gate = meta.get("activation_gate")
    if not gate:
        return True
    any_of = gate.get("any_of", [])
    min_s = gate.get("min_score", 0.30)
    return any(
        skill_graph.get(sid) is not None and skill_graph[sid].effective_score >= min_s
        for sid in any_of
    )


# ── Main planner ──────────────────────────────────────────────────────────────

def plan_next_milestone(state: LearnerState) -> PlanResult:
    """Run the 5-step planning algorithm and return the top milestone candidate."""

    # Step 0: Velocity
    velocity = compute_velocity(state)

    if velocity.re_engagement_mode:
        return PlanResult(top=None, horizon=[], velocity=velocity, re_engagement_mode=True)

    # Load model data
    skill_meta = _data.skill_metadata()
    depth = state.profile.desired_depth
    background = state.profile.background
    depth_thresh = _data.depth_threshold(depth)
    priority_weights = _data.role_priority_weights(background)
    depth_reqs = _data.role_requirements().get("domain_depth_requirements", {})

    # Skip list
    skip_set = {o.target for o in state.overrides if o.type == "not_interested"}

    # Step 1: Eligible skills
    eligible: dict[str, dict] = {}
    for skill_id, meta in skill_meta.items():
        s = state.skill_graph.get(skill_id)
        effective = s.effective_score if s else 0.0

        if effective >= depth_thresh:
            continue
        if skill_id in skip_set or meta["domain"] in skip_set:
            continue
        if not _prereqs_met(meta, state.skill_graph, velocity.tier):
            continue
        if not _activation_gate_met(meta, state.skill_graph):
            continue

        eligible[skill_id] = {
            "score": effective,
            "confidence": s.confidence if s else "low",
            "domain": meta["domain"],
            "name": meta["name"],
        }

    if not eligible:
        return PlanResult(
            top=None, horizon=[], velocity=velocity,
            no_eligible_skills=True, eligible_skill_count=0,
        )

    # Step 2: Gap priority
    conf_mult = {"high": 1.00, "medium": 1.10, "low": 1.20}
    vel_mult = max(velocity.multiplier, 0.90)  # floor at 0.90 to avoid zeroing scores

    # Momentum: domains with recent activity
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=30)
    momentum_domains: set[str] = set()
    for m in ([state.active_milestone] if state.active_milestone else []) + state.completed_milestones:
        ts_raw = getattr(m, "started_at", None) or getattr(m, "completed_at", None)
        if ts_raw:
            ts = ts_raw.replace(tzinfo=timezone.utc) if ts_raw.tzinfo is None else ts_raw
            if ts >= recent_cutoff:
                momentum_domains.add(m.domain)

    raw_priority: dict[str, float] = {}
    for skill_id, info in eligible.items():
        gap = max(0.0, depth_thresh - info["score"])
        role_w = priority_weights.get(info["domain"], 1.0)
        c_mult = conf_mult.get(info["confidence"], 1.10)
        mom_mult = 1.10 if info["domain"] in momentum_domains else 1.00
        raw_priority[skill_id] = gap * role_w * c_mult * mom_mult * vel_mult

    # Step 3: Unlock value bonus
    def blocked_count(skill_id: str) -> int:
        n = 0
        for other_id, other_meta in skill_meta.items():
            if skill_id not in other_meta.get("prerequisites", []):
                continue
            s = state.skill_graph.get(other_id)
            if (s is None or s.effective_score < depth_thresh):
                n += 1
        return n

    adjusted: dict[str, float] = {
        sid: raw_priority[sid] + blocked_count(sid) * 0.05
        for sid in raw_priority
    }

    # Step 4: Prerequisite chain resolution (promote unmet prereqs to top)
    sorted_skills = sorted(adjusted.items(), key=lambda x: x[1], reverse=True)

    if sorted_skills:
        top_id = sorted_skills[0][0]

        def lowest_unmet_prereq(skill_id: str, depth_limit: int = 5) -> str:
            if depth_limit <= 0:
                return skill_id
            meta = skill_meta.get(skill_id, {})
            min_thresh = meta.get("min_prerequisite_score", 0.30)
            for prereq_id in meta.get("prerequisites", []):
                prereq_s = state.skill_graph.get(prereq_id)
                prereq_score = prereq_s.effective_score if prereq_s else 0.0
                if prereq_score < min_thresh and prereq_id in eligible:
                    return lowest_unmet_prereq(prereq_id, depth_limit - 1)
            return skill_id

        promoted = lowest_unmet_prereq(top_id)
        if promoted != top_id:
            promo_p = adjusted.get(promoted, adjusted[top_id] + 0.01)
            sorted_skills = [(promoted, promo_p + 0.01)] + [
                (sid, p) for sid, p in sorted_skills if sid != promoted
            ]
            adjusted[promoted] = promo_p + 0.01

    # Step 5: Aggregate to domain milestones
    domain_skills: dict[str, dict[str, float]] = {}
    for skill_id, priority in adjusted.items():
        domain = eligible[skill_id]["domain"]
        domain_skills.setdefault(domain, {})[skill_id] = priority

    domain_names_map = {d["id"]: d["name"] for d in _data.domains()}
    candidates: list[MilestoneCandidate] = []

    for domain, dom_priorities in domain_skills.items():
        pvals = list(dom_priorities.values())
        domain_priority = 0.7 * max(pvals) + 0.3 * (sum(pvals) / len(pvals))

        # Target skills: prefer the domain's required skills for this depth
        depth_required = depth_reqs.get(domain, {}).get(depth, [])
        target = [sid for sid in depth_required if sid in eligible]
        if not target:
            target = sorted(dom_priorities, key=dom_priorities.get, reverse=True)[:4]  # type: ignore[arg-type]

        skill_scores = {
            sid: eligible[sid]["score"]
            for sid in target
            if sid in eligible
        }

        candidates.append(MilestoneCandidate(
            domain=domain,
            domain_name=domain_names_map.get(domain, domain),
            priority=domain_priority,
            target_skills=target,
            skill_priorities=dom_priorities,
            skill_scores=skill_scores,
        ))

    candidates.sort(key=lambda c: c.priority, reverse=True)

    return PlanResult(
        top=candidates[0] if candidates else None,
        horizon=candidates[1:4],
        velocity=velocity,
        eligible_skill_count=len(eligible),
    )
