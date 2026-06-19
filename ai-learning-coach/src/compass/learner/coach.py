"""Orchestration for the learner-centered coaching path.

Three LLM calls, each isolated behind its own seam function for test
monkeypatching, each parsed and validated before being trusted, each with a
deterministic fallback (with a fallback_reason) when the LLM is unavailable
or its response doesn't survive validation. Mirrors agent/coach.py's
evidence-bounded pattern, applied to open-ended learner-model claims instead
of a closed candidate set.
"""
from __future__ import annotations

import json

import openai

from ..config import OPENAI_API_KEY, OPENAI_MODEL
from .models import (
    BuildSpec,
    CapabilityClaim,
    CoachAssessment,
    CoachingCycle,
    CoachingRecommendation,
    EvidenceItem,
    LearnerCoachProfile,
    LearnerCoachState,
    UncertaintyClaim,
)
from .prompts import build_assessment_prompt, build_profile_update_prompt, build_recommendation_prompt
from .store import load_coach_state, save_coach_state
from .validation import (
    validate_belief,
    validate_capability,
    validate_gap,
    validate_growth_edge,
    validate_strength,
    validate_uncertainty,
)
from ..models import _now


# ── LLM seams ─────────────────────────────────────────────────────────────

def _call_openai(prompt: str) -> str | None:
    if not OPENAI_API_KEY:
        return None
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=2_000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except openai.OpenAIError:
        return None


def _request_llm_assessment(prompt: str) -> str | None:
    return _call_openai(prompt)


def _request_llm_profile_update(prompt: str) -> str | None:
    return _call_openai(prompt)


def _request_llm_recommendation(prompt: str) -> str | None:
    return _call_openai(prompt)


def _parse_json_object(raw: str | None) -> dict | None:
    if raw is None:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


# ── Stage 1: assessment ──────────────────────────────────────────────────

def _fallback_assessment(evidence: list[EvidenceItem], reason: str) -> CoachAssessment:
    by_skill: dict[str, list[str]] = {}
    for item in evidence:
        skill_id = item.metadata.get("skill_id")
        if skill_id:
            by_skill.setdefault(skill_id, []).append(item.id)

    capabilities = [
        CapabilityClaim(
            capability=skill_id,
            confidence=0.5,
            evidence_ids=ids,
            why_it_matters="Detected via deterministic evidence scan (LLM assessment unavailable).",
        )
        for skill_id, ids in sorted(by_skill.items())
    ]

    return CoachAssessment(
        current_stage="insufficient_llm_assessment",
        demonstrated_capabilities=capabilities,
        growth_gaps=[],
        uncertainties=[UncertaintyClaim(
            uncertainty="LLM coach assessment unavailable; learner model not updated beyond deterministic evidence.",
            missing_evidence=[],
            how_to_test="Re-run `compass learner coach` once an LLM is available.",
        )],
        learning_style_observations=[],
        coach_summary="Deterministic fallback — see demonstrated_capabilities for raw evidence-derived signals only.",
        source="deterministic_fallback",
        fallback_reason=reason,
    )


def assess_learner(profile: LearnerCoachProfile, evidence: list[EvidenceItem]) -> CoachAssessment:
    valid_ids = {item.id for item in evidence}
    prompt = build_assessment_prompt(profile, evidence)
    data = _parse_json_object(_request_llm_assessment(prompt))
    if data is None:
        return _fallback_assessment(evidence, "LLM unavailable or response could not be parsed as valid JSON")

    stage = str(data.get("current_stage", "")).strip()
    summary = str(data.get("coach_summary", "")).strip()
    if not stage or not summary:
        return _fallback_assessment(evidence, "LLM response missing required fields (current_stage/coach_summary)")

    capabilities = [c for c in (
        validate_capability(d, valid_ids) for d in data.get("demonstrated_capabilities", []) if isinstance(d, dict)
    ) if c]
    gaps = [g for g in (
        validate_gap(d, valid_ids) for d in data.get("growth_gaps", []) if isinstance(d, dict)
    ) if g]
    uncertainties = [u for u in (
        validate_uncertainty(d) for d in data.get("uncertainties", []) if isinstance(d, dict)
    ) if u]
    style_obs = [s.strip() for s in data.get("learning_style_observations", []) if isinstance(s, str) and s.strip()]

    return CoachAssessment(
        current_stage=stage,
        demonstrated_capabilities=capabilities,
        growth_gaps=gaps,
        uncertainties=uncertainties,
        learning_style_observations=style_obs,
        coach_summary=summary,
        source="llm",
        fallback_reason=None,
    )


# ── Stage 2: profile update ──────────────────────────────────────────────

def _fallback_profile_update(profile: LearnerCoachProfile, reason: str) -> LearnerCoachProfile:
    updated = profile.model_copy(deep=True)
    updated.uncertainties.append(UncertaintyClaim(
        uncertainty="Learner model not updated beyond previously recorded evidence.",
        missing_evidence=[],
        how_to_test=f"Re-run `compass learner coach` once an LLM is available. ({reason})",
    ))
    updated.updated_at = _now()
    return updated


def update_profile(
    profile: LearnerCoachProfile,
    evidence: list[EvidenceItem],
    assessment: CoachAssessment,
) -> LearnerCoachProfile:
    valid_ids = {item.id for item in evidence}
    prompt = build_profile_update_prompt(profile, evidence, assessment)
    data = _parse_json_object(_request_llm_profile_update(prompt))
    if data is None:
        return _fallback_profile_update(profile, "LLM unavailable or response could not be parsed as valid JSON")

    strengths = [s for s in (
        validate_strength(d, valid_ids) for d in data.get("strengths", []) if isinstance(d, dict)
    ) if s]
    growth_edges = [g for g in (
        validate_growth_edge(d, valid_ids) for d in data.get("growth_edges", []) if isinstance(d, dict)
    ) if g]
    coach_beliefs = [b for b in (
        validate_belief(d, valid_ids) for d in data.get("coach_beliefs", []) if isinstance(d, dict)
    ) if b]

    if not strengths and not growth_edges and not coach_beliefs:
        return _fallback_profile_update(profile, "LLM response contained no claims grounded in valid evidence ids")

    uncertainties = [u for u in (
        validate_uncertainty(d) for d in data.get("uncertainties", []) if isinstance(d, dict)
    ) if u]
    learning_style = [s.strip() for s in data.get("learning_style", []) if isinstance(s, str) and s.strip()]
    builder_patterns = [s.strip() for s in data.get("builder_patterns", []) if isinstance(s, str) and s.strip()]
    goals = [s.strip() for s in data.get("goals", []) if isinstance(s, str) and s.strip()] or profile.goals
    project_history = (
        [s.strip() for s in data.get("project_history", []) if isinstance(s, str) and s.strip()]
        or profile.project_history
    )

    return LearnerCoachProfile(
        learner_id=profile.learner_id,
        goals=goals,
        project_history=project_history,
        strengths=strengths,
        growth_edges=growth_edges,
        uncertainties=uncertainties,
        learning_style=learning_style,
        builder_patterns=builder_patterns,
        coach_beliefs=coach_beliefs,
        updated_at=_now(),
    )


# ── Stage 3: recommendation ──────────────────────────────────────────────

def _fallback_recommendation(learner_id: str, reason: str) -> CoachingRecommendation:
    next_challenge = "Review collected evidence and add a project reflection."
    evidence_hint: list[str] = []

    # Best-effort bridge to the legacy skill_graph/planner path, read-only —
    # any failure here must not break this fallback, so the catch is broad.
    try:
        from ..agent.planner import plan_next_milestone
        from ..memory.store import load_state as load_legacy_state

        legacy_state = load_legacy_state(learner_id)
        if legacy_state is not None:
            plan = plan_next_milestone(legacy_state)
            if plan.top is not None and plan.top.target_skills:
                next_challenge = (
                    f"Build toward {plan.top.domain_name} — target skill(s): "
                    f"{', '.join(plan.top.target_skills)}."
                )
                evidence_hint = list(plan.top.target_skills)
    except Exception:
        pass

    return CoachingRecommendation(
        next_challenge=next_challenge,
        why_this=f"AI coaching recommendation unavailable this run ({reason}).",
        targeted_growth_edges=[],
        build_spec=BuildSpec(project_goal=next_challenge),
        success_criteria=[],
        evidence_compass_will_look_for=evidence_hint,
        coach_note="Deterministic fallback — re-run once the AI coach is available for a tailored recommendation.",
        source="deterministic_fallback",
        fallback_reason=reason,
    )


def recommend_next_challenge(
    profile: LearnerCoachProfile,
    assessment: CoachAssessment,
    learner_id: str,
) -> CoachingRecommendation:
    prompt = build_recommendation_prompt(profile, assessment)
    data = _parse_json_object(_request_llm_recommendation(prompt))
    if data is None:
        return _fallback_recommendation(learner_id, "LLM unavailable or response could not be parsed as valid JSON")

    next_challenge = str(data.get("next_challenge", "")).strip()
    why_this = str(data.get("why_this", "")).strip()
    build_spec_raw = data.get("build_spec")
    if not next_challenge or not why_this or not isinstance(build_spec_raw, dict):
        return _fallback_recommendation(learner_id, "LLM response missing required fields (next_challenge/why_this/build_spec)")

    project_goal = str(build_spec_raw.get("project_goal", "")).strip()
    if not project_goal:
        return _fallback_recommendation(learner_id, "LLM response build_spec missing project_goal")

    build_spec = BuildSpec(
        project_goal=project_goal,
        required_capabilities=[s for s in build_spec_raw.get("required_capabilities", []) if isinstance(s, str) and s.strip()],
        suggested_artifacts=[s for s in build_spec_raw.get("suggested_artifacts", []) if isinstance(s, str) and s.strip()],
        constraints=[s for s in build_spec_raw.get("constraints", []) if isinstance(s, str) and s.strip()],
    )

    return CoachingRecommendation(
        next_challenge=next_challenge,
        why_this=why_this,
        targeted_growth_edges=[s for s in data.get("targeted_growth_edges", []) if isinstance(s, str) and s.strip()],
        build_spec=build_spec,
        success_criteria=[s for s in data.get("success_criteria", []) if isinstance(s, str) and s.strip()],
        evidence_compass_will_look_for=[
            s for s in data.get("evidence_compass_will_look_for", []) if isinstance(s, str) and s.strip()
        ],
        coach_note=str(data.get("coach_note", "")).strip(),
        source="llm",
        fallback_reason=None,
    )


# ── Top-level entrypoints ────────────────────────────────────────────────

def load_or_create_state(learner_id: str, goal: str | None = None) -> LearnerCoachState:
    state = load_coach_state(learner_id)
    if state is None:
        profile = LearnerCoachProfile(learner_id=learner_id, goals=[goal] if goal else [])
        return LearnerCoachState(profile=profile)
    if goal and goal not in state.profile.goals:
        state.profile.goals.append(goal)
    return state


def build_evidence_bundle(state: LearnerCoachState) -> list[EvidenceItem]:
    return [item for source in state.evidence_sources for item in source.items]


def run_coach(learner_id: str) -> LearnerCoachState:
    state = load_coach_state(learner_id)
    if state is None:
        raise ValueError(f"No learner-coach state found for '{learner_id}'. Run `compass learner init` first.")

    evidence = build_evidence_bundle(state)
    assessment = assess_learner(state.profile, evidence)
    updated_profile = update_profile(state.profile, evidence, assessment)
    recommendation = recommend_next_challenge(updated_profile, assessment, learner_id)

    state.profile = updated_profile
    state.history.append(CoachingCycle(
        evidence_count=len(evidence),
        assessment=assessment,
        recommendation=recommendation,
    ))
    save_coach_state(state)
    return state
