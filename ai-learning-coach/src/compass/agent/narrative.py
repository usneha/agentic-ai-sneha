"""Evidence-grounded narrative inference for `compass profile`/`explain`/`story`.

Every function here is fully deterministic — no LLM calls. They synthesize
already-persisted, evidence-backed structured data (skill_graph, evidence
ledger, planner output) into human-readable narrative fields. Nothing here
invents a skill, score, or date that isn't already backed by a SkillEvidence
record or a deterministic computation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import _data
from ..models import LearnerState
from .planner import plan_next_milestone


def _skill_name(skill_id: str) -> str:
    for dom in _data.skills()["domains"] + _data.skills().get("foundation_domains", []):
        for sub in dom["sub_skills"]:
            if sub["id"] == skill_id:
                return sub["name"]
    return skill_id


def confidence_label(current_score: float) -> str:
    """Recompute a confidence label directly from current_score.

    SkillScore.confidence is set once in assessor.py from the evidence-only
    score, *before* integration bonuses / foundation credits are added to
    current_score — so it can go stale (e.g. a skill boosted to 1.00 can
    still carry a "low" confidence label from before the boost). Narrative
    output recomputes it fresh here rather than trusting the stored field,
    so a skill display never contradicts its own score.
    """
    if current_score >= 0.7:
        return "high"
    if current_score >= 0.4:
        return "medium"
    return "low"


def zone(current: float, experience: float) -> str:
    """Classify a skill's evidence into core / dormant / learning / none.

    core    — actively demonstrated (current_score >= 0.50)
    dormant — demonstrated before but not recently reinforced, or only
              weakly/indirectly evidenced (current < 0.50, experience >= 0.40)
    learning — some real signal, not yet a strength
    none    — no evidence at all
    """
    if current >= 0.50:
        return "core"
    if experience >= 0.40:
        return "dormant"
    if current > 0.0 or experience > 0.0:
        return "learning"
    return "none"


_STRENGTH_CAP = 5
_EMERGING_CAP = 5


@dataclass
class ProfileNarrative:
    archetype: str
    secondary_clusters: list[str] = field(default_factory=list)
    emerging_clusters: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    emerging: list[str] = field(default_factory=list)
    foundation_skills: list[str] = field(default_factory=list)
    dormant_ai_skills: list[str] = field(default_factory=list)
    confidence_summary: str = ""
    recommended_direction: str = ""
    has_any_evidence: bool = False


def _archetype_aggregate_scores(sg: dict, ai_skill_ids: set[str]) -> dict[str, float]:
    """Sum of current_score across every evidenced skill in each archetype.

    Sum (not max or average) rewards breadth + depth together: an archetype
    with several genuinely-evidenced contributing skills outranks one where a
    single skill spiked from an integration bonus or foundation credit —
    representativeness over peak score. Skills map to archetypes via
    archetypes.yaml (_data.skill_archetype_map), not 1:1 to their raw domain
    — see that file for which domains/skills feed which archetype.
    """
    arch_map = _data.skill_archetype_map()
    totals: dict[str, float] = {}
    for skill_id, score in sg.items():
        if skill_id not in ai_skill_ids or score.current_score <= 0:
            continue
        arch_id = arch_map.get(skill_id)
        if arch_id:
            totals[arch_id] = totals.get(arch_id, 0.0) + score.current_score
    return totals


def _archetype_name(arch_id: str) -> str:
    return next((a["name"] for a in _data.archetypes()["archetypes"] if a["id"] == arch_id), arch_id)


def _catchall_archetype_id() -> str | None:
    return next((a["id"] for a in _data.archetypes()["archetypes"] if a.get("is_catchall")), None)


def _select_archetype(archetype_totals: dict[str, float]) -> tuple[list[str], list[str], list[str], float]:
    """Resolve archetype totals into (primary_ids, secondary_ids, emerging_ids, primary_total).

    primary_ids holds more than one id when two archetypes are near-equal
    (selection.co_primary_ratio) — shown together rather than forcing an
    arbitrary winner. A non-catchall archetype only wins the primary slot if
    it beats the catchall archetype's own total by
    selection.catchall_dominance_margin; otherwise the catchall (the general
    "AI Application Builder" identity) wins by default and the would-be
    specialized winner is demoted into secondary/emerging instead.
    """
    sel = _data.archetypes()["selection"]
    items = [(aid, total) for aid, total in archetype_totals.items() if total > 0]
    if not items:
        return [], [], [], 0.0

    by_id = dict(items)
    ranked = sorted(items, key=lambda x: x[1], reverse=True)
    top_id, top_total = ranked[0]

    catchall_id = _catchall_archetype_id()
    catchall_total = by_id.get(catchall_id, 0.0) if catchall_id else 0.0
    if catchall_id and top_id != catchall_id and top_total < sel["catchall_dominance_margin"] * catchall_total:
        top_id, top_total = catchall_id, catchall_total
        ranked = sorted(items, key=lambda x: (x[0] != top_id, -x[1]))

    rest = [(aid, total) for aid, total in ranked if aid != top_id]
    co_primary_ids = [aid for aid, total in rest if total >= sel["co_primary_ratio"] * top_total]
    primary_ids = [top_id] + co_primary_ids
    rest = [(aid, total) for aid, total in rest if aid not in co_primary_ids]

    secondary = [aid for aid, total in rest if total >= sel["secondary_ratio"] * top_total][: sel["max_secondary"]]
    emerging = [aid for aid, _ in rest if aid not in secondary][: sel["max_emerging"]]

    return primary_ids, secondary, emerging, top_total


def _recommended_direction_text(state: LearnerState) -> str:
    """Shared by profile's Recommended Direction and story's Likely Next Frontier."""
    plan = plan_next_milestone(state)
    if plan.re_engagement_mode:
        return "Resume momentum — re-engage with a recent repo before starting something new."
    if plan.no_eligible_skills or plan.top is None:
        return "All role-relevant skills are already above your target depth — consider exploring a new domain."
    return plan.top.domain_name


def build_profile_narrative(state: LearnerState) -> ProfileNarrative:
    sg = state.skill_graph
    ai_skill_ids = set(_data.all_skill_ids())
    foundation_skill_ids = set(_data.all_foundation_skill_ids())

    core: list[tuple[str, float]] = []
    learning: list[tuple[str, float]] = []
    dormant_ai: list[tuple[str, float]] = []
    foundation_evidenced: list[tuple[str, float]] = []

    for skill_id, score in sg.items():
        z = zone(score.current_score, score.experience_score)
        if skill_id in ai_skill_ids:
            if z == "core":
                core.append((skill_id, score.current_score))
            elif z == "learning":
                learning.append((skill_id, score.current_score))
            elif z == "dormant":
                dormant_ai.append((skill_id, score.experience_score))
        elif skill_id in foundation_skill_ids:
            if z in ("core", "dormant", "learning"):
                foundation_evidenced.append((skill_id, score.current_score))

    core.sort(key=lambda x: x[1], reverse=True)
    learning.sort(key=lambda x: x[1], reverse=True)
    dormant_ai.sort(key=lambda x: x[1], reverse=True)
    foundation_evidenced.sort(key=lambda x: x[1], reverse=True)

    # Archetype is the system category with the highest AGGREGATE evidence
    # across its contributing skills (breadth + depth), not the single
    # highest-scoring skill — see _archetype_aggregate_scores for why.
    fallbacks = _data.archetypes()["fallbacks"]
    min_evidence = _data.archetypes()["selection"]["min_evidence"]
    archetype_totals = _archetype_aggregate_scores(sg, ai_skill_ids)
    primary_ids, secondary_ids, emerging_ids, primary_total = _select_archetype(archetype_totals)

    named_archetype = False
    if not primary_ids:
        # No evidence in any AI domain at all — never claim an AI-builder
        # identity off foundation evidence alone.
        archetype = fallbacks["no_ai_evidence_with_foundation"] if foundation_evidenced else fallbacks["weak_ai_signal_below_minimum"]
    elif primary_total < min_evidence:
        # Some AI-domain evidence exists, but not enough to confidently name
        # a specific system-builder identity.
        archetype = fallbacks["weak_ai_signal_below_minimum"]
    else:
        archetype = " & ".join(_archetype_name(a) for a in primary_ids)
        named_archetype = True
    secondary_clusters = [_archetype_name(a) for a in secondary_ids]
    emerging_clusters = [_archetype_name(a) for a in emerging_ids]

    strengths = [_skill_name(sid) for sid, _ in core[:_STRENGTH_CAP]]
    emerging = [_skill_name(sid) for sid, _ in learning[:_EMERGING_CAP]]
    foundation_skills = [_skill_name(sid) for sid, _ in foundation_evidenced]
    dormant_ai_skills = [_skill_name(sid) for sid, _ in dormant_ai]

    # Confidence summary — counts across strengths + emerging only (the
    # skills actually being surfaced), never raw scores in the headline.
    counted_ids = [sid for sid, _ in core[:_STRENGTH_CAP]] + [sid for sid, _ in learning[:_EMERGING_CAP]]
    conf_counts = {"high": 0, "medium": 0, "low": 0}
    for sid in counted_ids:
        conf_counts[confidence_label(sg[sid].current_score)] += 1

    if not counted_ids:
        confidence_summary = "Not enough evidence yet to summarize confidence — scan a repo to get started."
    else:
        parts = []
        if conf_counts["high"]:
            parts.append(f"{conf_counts['high']} demonstrated with high confidence")
        if conf_counts["medium"]:
            parts.append(f"{conf_counts['medium']} with moderate confidence")
        if conf_counts["low"]:
            parts.append(f"{conf_counts['low']} with early/low confidence")
        summary = ", ".join(parts)
        if named_archetype:
            confidence_summary = f"{summary} — your strongest evidence is concentrated in {archetype}."
        else:
            confidence_summary = f"{summary}."

    return ProfileNarrative(
        archetype=archetype,
        secondary_clusters=secondary_clusters,
        emerging_clusters=emerging_clusters,
        strengths=strengths,
        emerging=emerging,
        foundation_skills=foundation_skills,
        dormant_ai_skills=dormant_ai_skills,
        confidence_summary=confidence_summary,
        recommended_direction=_recommended_direction_text(state),
        has_any_evidence=bool(core or learning or dormant_ai or foundation_evidenced),
    )


# ── Story ────────────────────────────────────────────────────────────────────

_TOP_SKILLS_PER_CHAPTER = 3


@dataclass
class StoryChapter:
    year: str
    text: str


@dataclass
class StoryNarrative:
    chapters: list[StoryChapter] = field(default_factory=list)
    today_text: str = ""
    next_frontier: str = ""
    insufficient_history: bool = False


def _repo_chapter_text(state: LearnerState, repo_name: str) -> str:
    """Build one evidence-grounded sentence describing what was built in a repo."""
    ai_ids = set(_data.all_skill_ids())
    domain_map = _data.skill_domain_map()

    records = [
        ev for ev in state.evidence
        if ev.source_repo == repo_name and ev.source == "scan" and ev.evidence_type == "observed"
    ]
    best: dict[str, int] = {}
    for ev in records:
        if ev.confidence > best.get(ev.skill_id, -1):
            best[ev.skill_id] = ev.confidence

    ai_hits = {sid: c for sid, c in best.items() if sid in ai_ids}
    foundation_hits = {sid: c for sid, c in best.items() if sid not in ai_ids}

    if ai_hits:
        domain_counts: dict[str, int] = {}
        for sid in ai_hits:
            dom = domain_map.get(sid)
            if dom:
                domain_counts[dom] = domain_counts.get(dom, 0) + 1
        dominant_domain = max(domain_counts, key=domain_counts.get)
        dominant_domain_name = next(
            (d["name"] for d in _data.domains() if d["id"] == dominant_domain), dominant_domain
        )
        # Top skills must come FROM the dominant domain — otherwise the
        # sentence can name a domain and then list unrelated skills from a
        # different domain that happened to score higher confidence.
        in_domain_hits = {sid: c for sid, c in ai_hits.items() if domain_map.get(sid) == dominant_domain}
        top_skills = sorted(in_domain_hits, key=in_domain_hits.get, reverse=True)[:_TOP_SKILLS_PER_CHAPTER]
        skill_names = ", ".join(_skill_name(sid) for sid in top_skills)
        return f"Built in {dominant_domain_name}: {skill_names} ({repo_name})."

    if foundation_hits:
        top_skills = sorted(foundation_hits, key=foundation_hits.get, reverse=True)[:_TOP_SKILLS_PER_CHAPTER]
        skill_names = ", ".join(_skill_name(sid) for sid in top_skills)
        return f"Built using {skill_names} ({repo_name})."

    return f"Worked on {repo_name}."


def build_story_narrative(state: LearnerState) -> StoryNarrative:
    cache = state.github_cache
    if cache is None or not cache.repo_chronology:
        return StoryNarrative(insufficient_history=True)

    evidenced_repos = {ev.source_repo for ev in state.evidence if ev.source_repo}

    # Qualifying repos: real git history (non-None first_commit_date) AND at
    # least one credited skill — git history alone isn't a "chapter".
    qualifying: list[tuple[str, str, str | None]] = []  # (first_date, repo_name, last_date)
    for repo_name, dates in cache.repo_chronology.items():
        first_date = dates.get("first_commit_date")
        if not first_date or repo_name not in evidenced_repos:
            continue
        qualifying.append((first_date, repo_name, dates.get("last_commit_date")))

    if not qualifying:
        return StoryNarrative(insufficient_history=True)

    qualifying.sort(key=lambda x: x[0])

    chapters = [
        StoryChapter(year=first_date[:4], text=_repo_chapter_text(state, repo_name))
        for first_date, repo_name, _last_date in qualifying
    ]

    most_recent_last = max((last for _, _, last in qualifying if last), default=None)
    today_text = (
        f"Most recent activity: {most_recent_last}."
        if most_recent_last else "No recent activity recorded yet."
    )

    return StoryNarrative(
        chapters=chapters,
        today_text=today_text,
        next_frontier=_recommended_direction_text(state),
        insufficient_history=False,
    )
