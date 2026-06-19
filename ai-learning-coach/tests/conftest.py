"""Shared in-memory learner-state fixtures for tests.

Built fully in-memory (no data/learners/ disk dependency, no save_state
call) by replaying SkillEvidence through the real apply_evidence() —
the same recomputation path compass run/scan use — so skill_graph scores
are real aggregator output, not hand-faked numbers.
"""
from __future__ import annotations

import pytest

from compass.agent import coach as coach_module
from compass.cli import build_initial_skill_graph
from compass.competency.assessor import apply_evidence
from compass.learner import coach as learner_coach_module
from compass.models import LearnerProfile, LearnerState, SkillEvidence


@pytest.fixture(autouse=True)
def no_real_llm_calls(monkeypatch):
    """Tests must never hit the real OpenAI API. Default to "LLM unavailable"
    (forces the deterministic fallback path); individual tests override
    `compass.agent.coach._request_llm_choice` to simulate a specific response."""
    monkeypatch.setattr(coach_module, "_request_llm_choice", lambda prompt: None)
    monkeypatch.setattr(learner_coach_module, "_request_llm_assessment", lambda prompt: None)
    monkeypatch.setattr(learner_coach_module, "_request_llm_profile_update", lambda prompt: None)
    monkeypatch.setattr(learner_coach_module, "_request_llm_recommendation", lambda prompt: None)


def make_state(evidence_skill_ids: list[str], repo_name: str, background: str = "software_engineer") -> LearnerState:
    profile = LearnerProfile(
        name="Test Learner",
        background=background,
        desired_depth="practitioner",
        learning_style="build_first",
    )
    state = LearnerState(
        profile=profile,
        skill_graph=build_initial_skill_graph(background),
    )
    state.evidence = [
        SkillEvidence(
            skill_id=skill_id,
            evidence_type="observed",
            recency="current",
            confidence=85,
            source_repo=repo_name,
            source="scan",
        )
        for skill_id in evidence_skill_ids
    ]
    apply_evidence(state)
    return state


@pytest.fixture
def t_repo_state() -> LearnerState:
    """No evidence at all — an empty/unscanned repo."""
    return make_state([], repo_name="t-repo")


@pytest.fixture
def itmo_state() -> LearnerState:
    """Foundation software evidence only, zero AI-domain evidence."""
    return make_state(
        ["foundation.backend", "foundation.cloud_services", "foundation.databases"],
        repo_name="itmo-544-mp1",
    )


@pytest.fixture
def course_rag_state() -> LearnerState:
    """RAG + light-eval evidence, mirroring the real course-rag fixture."""
    return make_state(
        [
            "rag.embeddings", "rag.chunking", "rag.retrieval_basic",
            "eval.datasets", "eval.generation_metrics",
        ],
        repo_name="course-rag",
    )


@pytest.fixture
def shikhu_state() -> LearnerState:
    """Prompting + light-eval + light-agents + light-deployment, mirroring shikhu."""
    return make_state(
        [
            "prompting.basic", "prompting.structured", "prompting.iteration",
            "rag.ingestion", "eval.datasets", "agents.tool_use", "deployment.cicd",
        ],
        repo_name="shikhu",
    )
