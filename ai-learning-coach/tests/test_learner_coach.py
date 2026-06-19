"""Tests for the learner-centered coaching path (compass/learner/).

The real OpenAI calls are never exercised (conftest's autouse fixture
forces all three learner-coach LLM seams to return None by default).
Individual tests monkeypatch the seam they care about to simulate a
specific LLM response, and verify the hard rule: any claim citing an
evidence id that doesn't exist in the bundle gets dropped, and a fully
unsupported/malformed response falls back to a deterministic result with
a fallback_reason.
"""
from __future__ import annotations

import json

import pytest

from compass.learner import coach as learner_coach
from compass.learner.evidence import collect_doc_evidence, collect_repo_evidence
from compass.learner.models import EvidenceItem, EvidenceSource, LearnerCoachProfile, LearnerCoachState
from conftest import make_state


def _evidence_bundle() -> list[EvidenceItem]:
    return [
        EvidenceItem(source_id="course-rag", source_type="github_repo", summary="Implemented hybrid retrieval", metadata={"skill_id": "rag.hybrid"}),
        EvidenceItem(source_id="course-rag", source_type="github_repo", summary="Built an eval harness with golden datasets", metadata={"skill_id": "eval.datasets"}),
    ]


# ── Evidence collection ──────────────────────────────────────────────────

def test_collect_doc_evidence_splits_paragraphs(tmp_path):
    doc = tmp_path / "reflection.md"
    doc.write_text("First paragraph about a project.\n\nSecond paragraph about growth.")

    source = collect_doc_evidence(doc, "reflection")

    assert source.source_type == "reflection"
    assert len(source.items) == 2
    assert source.items[0].artifact_path == str(doc)
    assert "First paragraph" in source.items[0].quote


def test_collect_repo_evidence_smoke(tmp_path):
    (tmp_path / "README.md").write_text("# empty project")

    source = collect_repo_evidence(tmp_path)

    assert source.source_type == "github_repo"
    assert source.source_name == tmp_path.name


def test_build_evidence_bundle_flattens_multiple_sources():
    profile = LearnerCoachProfile(learner_id="t1")
    state = LearnerCoachState(
        profile=profile,
        evidence_sources=[
            EvidenceSource(source_type="doc", source_name="a", items=[EvidenceItem(source_id="a", source_type="doc", summary="x")]),
            EvidenceSource(source_type="blog", source_name="b", items=[EvidenceItem(source_id="b", source_type="blog", summary="y")]),
        ],
    )

    bundle = learner_coach.build_evidence_bundle(state)
    assert len(bundle) == 2


# ── Stage 1: assessment ───────────────────────────────────────────────────

def test_assess_learner_valid_response_is_used(monkeypatch):
    evidence = _evidence_bundle()
    profile = LearnerCoachProfile(learner_id="t1")
    monkeypatch.setattr(learner_coach, "_request_llm_assessment", lambda prompt: json.dumps({
        "current_stage": "practitioner",
        "demonstrated_capabilities": [
            {"capability": "Hybrid retrieval design", "confidence": 0.8, "evidence_ids": [evidence[0].id], "why_it_matters": "core RAG skill"},
        ],
        "growth_gaps": [],
        "uncertainties": [],
        "learning_style_observations": ["build_first"],
        "coach_summary": "Solid RAG fundamentals.",
    }))

    assessment = learner_coach.assess_learner(profile, evidence)

    assert assessment.source == "llm"
    assert assessment.fallback_reason is None
    assert len(assessment.demonstrated_capabilities) == 1
    assert assessment.demonstrated_capabilities[0].evidence_ids == [evidence[0].id]


def test_assess_learner_drops_claim_with_invented_evidence_id(monkeypatch):
    evidence = _evidence_bundle()
    profile = LearnerCoachProfile(learner_id="t1")
    monkeypatch.setattr(learner_coach, "_request_llm_assessment", lambda prompt: json.dumps({
        "current_stage": "practitioner",
        "demonstrated_capabilities": [
            {"capability": "Invented capability", "confidence": 0.9, "evidence_ids": ["ev_doesnotexist"], "why_it_matters": "n/a"},
        ],
        "growth_gaps": [],
        "uncertainties": [],
        "learning_style_observations": [],
        "coach_summary": "Summary present.",
    }))

    assessment = learner_coach.assess_learner(profile, evidence)

    assert assessment.source == "llm"
    assert assessment.demonstrated_capabilities == []


def test_assess_learner_malformed_json_falls_back(monkeypatch):
    evidence = _evidence_bundle()
    profile = LearnerCoachProfile(learner_id="t1")
    monkeypatch.setattr(learner_coach, "_request_llm_assessment", lambda prompt: "not json")

    assessment = learner_coach.assess_learner(profile, evidence)

    assert assessment.source == "deterministic_fallback"
    assert assessment.fallback_reason is not None
    assert assessment.current_stage == "insufficient_llm_assessment"
    # Deterministic fallback still derives capabilities from evidence metadata.
    assert {c.capability for c in assessment.demonstrated_capabilities} == {"rag.hybrid", "eval.datasets"}


# ── Stage 2: profile update ─────────────────────────────────────────────

def test_update_profile_valid_response_is_used(monkeypatch):
    evidence = _evidence_bundle()
    profile = LearnerCoachProfile(learner_id="t1")
    assessment = learner_coach._fallback_assessment(evidence, "n/a")
    monkeypatch.setattr(learner_coach, "_request_llm_profile_update", lambda prompt: json.dumps({
        "goals": ["Become strong at agentic AI systems"],
        "project_history": ["course-rag"],
        "strengths": [{"strength": "Hybrid retrieval design", "confidence": 0.8, "evidence_ids": [evidence[0].id]}],
        "growth_edges": [],
        "uncertainties": [],
        "learning_style": ["build_first"],
        "builder_patterns": [],
        "coach_beliefs": [],
    }))

    updated = learner_coach.update_profile(profile, evidence, assessment)

    assert updated.learner_id == "t1"
    assert len(updated.strengths) == 1
    assert updated.strengths[0].evidence_ids == [evidence[0].id]
    assert updated.goals == ["Become strong at agentic AI systems"]


def test_update_profile_malformed_json_falls_back_and_preserves_prior_state(monkeypatch):
    evidence = _evidence_bundle()
    profile = LearnerCoachProfile(learner_id="t1", goals=["existing goal"])
    assessment = learner_coach._fallback_assessment(evidence, "n/a")
    monkeypatch.setattr(learner_coach, "_request_llm_profile_update", lambda prompt: None)

    updated = learner_coach.update_profile(profile, evidence, assessment)

    assert updated.goals == ["existing goal"]
    assert any("not updated" in u.uncertainty for u in updated.uncertainties)


def test_update_profile_with_no_grounded_claims_falls_back(monkeypatch):
    evidence = _evidence_bundle()
    profile = LearnerCoachProfile(learner_id="t1")
    assessment = learner_coach._fallback_assessment(evidence, "n/a")
    monkeypatch.setattr(learner_coach, "_request_llm_profile_update", lambda prompt: json.dumps({
        "strengths": [{"strength": "Fabricated", "confidence": 0.9, "evidence_ids": ["ev_fake"]}],
        "growth_edges": [],
        "coach_beliefs": [],
    }))

    updated = learner_coach.update_profile(profile, evidence, assessment)

    assert updated.strengths == []
    assert any("not updated" in u.uncertainty for u in updated.uncertainties)


# ── Stage 3: recommendation ──────────────────────────────────────────────

def test_recommend_next_challenge_valid_response_is_used(monkeypatch):
    profile = LearnerCoachProfile(learner_id="t1")
    assessment = learner_coach._fallback_assessment([], "n/a")
    monkeypatch.setattr(learner_coach, "_request_llm_recommendation", lambda prompt: json.dumps({
        "next_challenge": "Build a multi-hop RAG eval harness",
        "why_this": "Targets the reranking growth edge with observable evidence.",
        "targeted_growth_edges": ["reranking"],
        "build_spec": {"project_goal": "Multi-hop RAG eval harness", "required_capabilities": [], "suggested_artifacts": [], "constraints": []},
        "success_criteria": ["Eval harness scores 3 retrieval strategies"],
        "evidence_compass_will_look_for": ["eval harness code"],
        "coach_note": "",
    }))

    rec = learner_coach.recommend_next_challenge(profile, assessment, "t1")

    assert rec.source == "llm"
    assert rec.next_challenge == "Build a multi-hop RAG eval harness"


def test_recommend_next_challenge_falls_back_to_generic_text_with_no_legacy_state(monkeypatch):
    profile = LearnerCoachProfile(learner_id="learner-with-no-legacy-state")
    assessment = learner_coach._fallback_assessment([], "n/a")
    monkeypatch.setattr(learner_coach, "_request_llm_recommendation", lambda prompt: "not json")

    rec = learner_coach.recommend_next_challenge(profile, assessment, "learner-with-no-legacy-state")

    assert rec.source == "deterministic_fallback"
    assert rec.next_challenge == "Review collected evidence and add a project reflection."


def test_recommendation_fallback_bridges_to_legacy_planner(tmp_path, monkeypatch):
    """If a legacy skill_graph LearnerState exists for this learner_id, the
    deterministic fallback should suggest the planner's actual top pick
    instead of the generic text — read-only bridge to the old path."""
    monkeypatch.setattr("compass.memory.store.LEARNERS_DIR", tmp_path)
    from compass.memory.store import save_state

    legacy_state = make_state(
        ["rag.embeddings", "rag.chunking", "rag.retrieval_basic", "eval.datasets", "eval.generation_metrics"],
        repo_name="course-rag",
    )
    legacy_state.profile.learner_id = "bridge-learner"
    save_state(legacy_state)

    rec = learner_coach._fallback_recommendation("bridge-learner", "test reason")

    assert rec.source == "deterministic_fallback"
    assert rec.next_challenge != "Review collected evidence and add a project reflection."


# ── End-to-end ────────────────────────────────────────────────────────────

def test_run_coach_persists_state_across_runs(tmp_path, monkeypatch):
    monkeypatch.setattr("compass.learner.store.LEARNERS_DIR", tmp_path)
    from compass.learner.store import load_coach_state, save_coach_state

    state = learner_coach.load_or_create_state("e2e-learner", goal="Become strong at agentic AI systems")
    state.evidence_sources.append(EvidenceSource(
        source_type="reflection", source_name="r1",
        items=[EvidenceItem(source_id="r1", source_type="reflection", summary="Reflected on a RAG project")],
    ))
    save_coach_state(state)

    result = learner_coach.run_coach("e2e-learner")

    assert result.latest_assessment.source == "deterministic_fallback"
    assert result.latest_recommendation.source == "deterministic_fallback"

    reloaded = load_coach_state("e2e-learner")
    assert reloaded.latest_assessment.source == "deterministic_fallback"
    assert reloaded.profile.goals == ["Become strong at agentic AI systems"]
