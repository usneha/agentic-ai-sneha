"""Agentic run pipeline for `compass run`.

Orchestrates six steps against a single repo and produces a RunTrace
recording what each step did, for `compass trace <run_id>`:

  1. repo_scan          — deterministic evidence + file inventory (scanner.py)
  2. repo_analyze       — lightweight LLM assessment (llm_assessor.py)
  3. divergence_check    — LLM-vs-deterministic guardrails (llm_assessor.apply_guardrails)
  4. evidence_update     — append SkillEvidence records to the persistent ledger
  5. profile_recompute   — recompute current_score / experience_score (assessor.py)
  6. recommendation      — next milestone (planner.py)

This module does not change the scoring formula in aggregator.py — it only
maps LLM-assessed skills onto the evidence_type/recency weight tiers that
already exist there, and records what happened at each step for tracing.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..competency.assessor import apply_evidence
from ..competency.corrections import index_corrections
from ..evidence.llm_assessor import apply_guardrails, assess_repo_traced
from ..evidence.scanner import scan_repo
from ..models import (
    DivergenceFlag,
    GitHubCache,
    LearnerState,
    RunTrace,
    SkillAggregationTrace,
    SkillEvidence,
    ToolCallRecord,
    _now,
)
from .planner import plan_next_milestone

# LLM evidence is always weighted at or below deterministic "observed" evidence —
# see aggregator.py's _CURRENT_TYPE_WEIGHT / _EXPERIENCE_TYPE_WEIGHT tiers.
_LLM_EVIDENCE_TYPE_MAP = {
    "current_demonstrated": "inferred",
    "historical_experience": "inferred",
    "inferred_exposure": "synthesized",
    "inferred_low_confidence": "synthesized",
}
_LLM_RECENCY_MAP = {
    "current_demonstrated": "current",
    "historical_experience": "historical",
}


def _step(steps: list[ToolCallRecord], name: str, t0: float, inputs: dict, outputs: dict, error: str | None = None) -> None:
    steps.append(ToolCallRecord(
        step=name,
        duration_ms=int((time.time() - t0) * 1000),
        inputs=inputs,
        outputs=outputs,
        error=error,
    ))


def _llm_skills_to_evidence(assessment, repo_recency: str) -> list[SkillEvidence]:
    """Convert LLM-assessed skills into SkillEvidence records for the ledger."""
    out: list[SkillEvidence] = []
    for skill in assessment.skills:
        ev_type = _LLM_EVIDENCE_TYPE_MAP.get(skill.evidence_type, "synthesized")
        recency = _LLM_RECENCY_MAP.get(skill.evidence_type, repo_recency)
        out.append(SkillEvidence(
            skill_id=skill.skill_id,
            evidence_type=ev_type,
            recency=recency,
            confidence=round(skill.confidence * 100),
            source_repo=assessment.repo_name,
            source="llm",
            rationale=skill.rationale,
        ))
    return out


def run_pipeline(state: LearnerState, repo_path: Path) -> RunTrace:
    """Run the full agentic pipeline for one repo against `state`.

    Mutates `state` in place (evidence, github_cache, llm_assessments,
    skill_graph, active_milestone is NOT set here — recommendation is
    surfaced but left for the caller to accept). Caller is responsible for
    save_state(state) and persisting the returned trace.
    """
    repo_path = repo_path.resolve()
    repo_name = repo_path.name
    trace = RunTrace(
        learner_id=state.profile.learner_id,
        repo_name=repo_name,
        repo_path=str(repo_path),
    )

    # ── Step 1: repo_scan ────────────────────────────────────────────────
    t0 = time.time()
    scan_result = scan_repo(repo_path)
    _step(
        trace.steps, "repo_scan", t0,
        inputs={"repo_path": str(repo_path)},
        outputs={
            "files_scanned": scan_result.files_scanned,
            "deterministic_evidence_records": len(scan_result.evidence),
            "scan_errors": scan_result.errors,
        },
    )

    # ── Step 2: repo_analyze (LLM) ───────────────────────────────────────
    t0 = time.time()
    llm_assessment, llm_debug = assess_repo_traced(repo_path)
    trace.llm_prompt = llm_debug.prompt
    trace.llm_response = llm_debug.raw_response
    trace.files_sampled = llm_debug.sampled_files
    _step(
        trace.steps, "repo_analyze", t0,
        inputs={"repo_path": str(repo_path), "files_sampled": llm_debug.sampled_files},
        outputs={
            "skills_assessed": len(llm_assessment.skills),
            "repo_recency": llm_assessment.repo_recency,
            "model": llm_assessment.model,
            "error": llm_assessment.error,
        },
        error=llm_assessment.error,
    )

    # ── Step 3: divergence_check ─────────────────────────────────────────
    # Compares LLM confidence against the CURRENT (pre-update) skill graph,
    # before this run's new evidence is merged in.
    t0 = time.time()
    divergence_flags: list[DivergenceFlag] = []
    if not llm_assessment.error:
        apply_guardrails(llm_assessment, state.skill_graph)
        corrections_index = index_corrections(state.corrections)
        # Flag both real divergence (high LLM confidence, zero deterministic score)
        # and weak/generic evidence (rationale lacks a concrete reference) — both
        # are review-worthy, surfaced together via `compass review`.
        for skill in llm_assessment.skills:
            if skill.needs_review or skill.evidence_type == "inferred_low_confidence":
                det = state.skill_graph.get(skill.skill_id)
                flag = DivergenceFlag(
                    skill_id=skill.skill_id,
                    llm_confidence=skill.confidence,
                    deterministic_score=det.effective_score if det else 0.0,
                    reason=skill.review_reason or "weak/generic evidence",
                )
                # If the learner already made a decision for this (skill, repo),
                # carry it forward instead of re-flagging it as unresolved.
                existing = corrections_index.get((skill.skill_id, repo_name)) or corrections_index.get((skill.skill_id, None))
                if existing:
                    flag.resolved = True
                    flag.correction_id = existing.correction_id
                divergence_flags.append(flag)
    trace.divergence_flags = divergence_flags
    _step(
        trace.steps, "divergence_check", t0,
        inputs={"skills_checked": len(llm_assessment.skills)},
        outputs={"flagged": len(divergence_flags), "flagged_skills": [f.skill_id for f in divergence_flags]},
    )

    # ── Step 4: evidence_update ──────────────────────────────────────────
    t0 = time.time()
    llm_evidence = _llm_skills_to_evidence(llm_assessment, llm_assessment.repo_recency) if not llm_assessment.error else []
    new_evidence = list(scan_result.evidence) + llm_evidence

    # Replace any prior evidence for this repo, then add the fresh records.
    state.evidence = [e for e in state.evidence if e.source_repo != repo_name]
    state.evidence.extend(new_evidence)

    cache = state.github_cache or GitHubCache()
    if repo_name not in cache.repos:
        cache.repos.append(repo_name)
    cache.files_scanned = scan_result.files_scanned
    cache.scan_errors = scan_result.errors
    cache.last_scan = _now()
    state.github_cache = cache

    if not llm_assessment.error:
        state.llm_assessments = [a for a in state.llm_assessments if a.repo_name != repo_name]
        state.llm_assessments.append(llm_assessment)

    trace.evidence_created = new_evidence
    _step(
        trace.steps, "evidence_update", t0,
        inputs={"deterministic_records": len(scan_result.evidence), "llm_records": len(llm_evidence)},
        outputs={"total_evidence_for_repo": len(new_evidence)},
    )

    # ── Step 5: profile_recompute ────────────────────────────────────────
    t0 = time.time()
    assess_result = apply_evidence(state)
    touched_skills = {ev.skill_id for ev in new_evidence}
    trace.aggregation = [
        SkillAggregationTrace(
            skill_id=skill_id,
            contributions=assess_result.aggregation_detail.get(skill_id, []),
            current_score=state.skill_graph[skill_id].current_score,
            experience_score=state.skill_graph[skill_id].experience_score,
        )
        for skill_id in sorted(touched_skills)
        if skill_id in state.skill_graph
    ]
    _step(
        trace.steps, "profile_recompute", t0,
        inputs={"skills_touched": len(touched_skills)},
        outputs={
            "skills_updated": len(assess_result.updated_skills),
            "integration_bonuses": [f"{a}+{b}" for a, b in assess_result.integration_bonuses],
        },
    )

    # ── Step 6: recommendation ───────────────────────────────────────────
    t0 = time.time()
    plan = plan_next_milestone(state)
    if plan.re_engagement_mode:
        rec_summary = {"re_engagement_mode": True}
    elif plan.no_eligible_skills or plan.top is None:
        rec_summary = {"no_eligible_skills": True}
    else:
        rec_summary = {
            "domain": plan.top.domain,
            "domain_name": plan.top.domain_name,
            "priority": plan.top.priority,
            "target_skills": plan.top.target_skills,
            "velocity_signal": plan.velocity.signal,
        }
    trace.recommendation_summary = rec_summary
    _step(
        trace.steps, "recommendation", t0,
        inputs={"velocity_signal": plan.velocity.signal},
        outputs=rec_summary,
    )

    trace.completed_at = _now()
    return trace
