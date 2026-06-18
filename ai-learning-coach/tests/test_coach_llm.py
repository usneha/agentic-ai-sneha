"""Tests for the evidence-bounded LLM coaching layer in coach.py.

The real OpenAI call is never exercised here (conftest's autouse fixture
forces `_request_llm_choice` to return None by default) — these tests
monkeypatch that single seam to simulate specific LLM responses and verify
hard validation: a valid in-bounds choice is used, anything that references
a skill outside the eligible/near-eligible candidate packet (or is
malformed) falls back to the deterministic planner pick.
"""
from __future__ import annotations

import json

import pytest

from compass import _data
from compass.agent import coach as coach_module
from compass.agent.coach import _demonstrated_core_skill_ids_ranked, build_candidate_packet, build_coaching_recommendation
from compass.agent.planner import plan_next_milestone
from conftest import make_state


def _patch_llm(monkeypatch, raw: str | None):
    monkeypatch.setattr(coach_module, "_request_llm_choice", lambda prompt: raw)


def test_valid_eligible_choice_is_used(course_rag_state, monkeypatch):
    packet = build_candidate_packet(course_rag_state)
    eligible_id = packet.eligible[0].skill_id
    _patch_llm(monkeypatch, json.dumps({
        "chosen_skill_id": eligible_id,
        "alternative_skill_id": None,
        "rationale": "Custom LLM rationale referencing only given facts.",
        "alternative_rationale": None,
    }))

    rec = build_coaching_recommendation(course_rag_state)
    assert rec.source == "llm"
    assert rec.fallback_reason is None
    assert rec.target_skill_id == eligible_id
    assert rec.rationale == "Custom LLM rationale referencing only given facts."


def test_valid_near_eligible_choice_is_used(course_rag_state, monkeypatch):
    packet = build_candidate_packet(course_rag_state)
    assert packet.near_eligible, "fixture must have a near-eligible candidate for this test"
    near_id = packet.near_eligible[0].skill_id
    _patch_llm(monkeypatch, json.dumps({
        "chosen_skill_id": near_id,
        "alternative_skill_id": None,
        "rationale": "Picking the near-eligible skill.",
        "alternative_rationale": None,
    }))

    rec = build_coaching_recommendation(course_rag_state)
    assert rec.source == "llm"
    assert rec.target_skill_id == near_id


def test_llm_choosing_a_blocked_skill_falls_back(course_rag_state, monkeypatch):
    packet = build_candidate_packet(course_rag_state)
    assert packet.blocked_relevant, "fixture must have a blocked-relevant candidate for this test"
    blocked_id = packet.blocked_relevant[0].skill_id
    _patch_llm(monkeypatch, json.dumps({
        "chosen_skill_id": blocked_id,
        "alternative_skill_id": None,
        "rationale": "Trying to pick a blocked skill.",
        "alternative_rationale": None,
    }))

    plan = plan_next_milestone(course_rag_state)
    expected_fallback = plan.top.target_skills[0] if plan.top.target_skills else max(plan.top.skill_priorities, key=plan.top.skill_priorities.get)

    rec = build_coaching_recommendation(course_rag_state)
    assert rec.source == "deterministic"
    assert rec.fallback_reason is not None
    assert rec.target_skill_id == expected_fallback


def test_llm_inventing_a_skill_id_falls_back(course_rag_state, monkeypatch):
    _patch_llm(monkeypatch, json.dumps({
        "chosen_skill_id": "totally.invented.skill",
        "alternative_skill_id": None,
        "rationale": "This skill does not exist.",
        "alternative_rationale": None,
    }))

    rec = build_coaching_recommendation(course_rag_state)
    assert rec.source == "deterministic"
    assert rec.target_skill_id in _data.all_skill_ids()


def test_llm_malformed_json_falls_back(course_rag_state, monkeypatch):
    _patch_llm(monkeypatch, "this is not json")
    rec = build_coaching_recommendation(course_rag_state)
    assert rec.source == "deterministic"
    assert "parsed" in rec.fallback_reason


def test_llm_missing_rationale_falls_back(course_rag_state, monkeypatch):
    packet = build_candidate_packet(course_rag_state)
    eligible_id = packet.eligible[0].skill_id
    _patch_llm(monkeypatch, json.dumps({"chosen_skill_id": eligible_id, "rationale": ""}))
    rec = build_coaching_recommendation(course_rag_state)
    assert rec.source == "deterministic"


def test_invalid_alternative_invalidates_whole_response(course_rag_state, monkeypatch):
    """All-or-nothing: a valid chosen skill paired with an invented alternative
    must not be partially trusted — the whole response falls back."""
    packet = build_candidate_packet(course_rag_state)
    eligible_id = packet.eligible[0].skill_id
    _patch_llm(monkeypatch, json.dumps({
        "chosen_skill_id": eligible_id,
        "alternative_skill_id": "made.up.alternative",
        "rationale": "Valid chosen skill, invented alternative.",
        "alternative_rationale": "Also invented.",
    }))

    rec = build_coaching_recommendation(course_rag_state)
    assert rec.source == "deterministic"
    assert rec.fallback_reason is not None


def test_build_suggestion_and_evidence_are_always_grounded_lookups(course_rag_state, monkeypatch):
    """build_suggestion and confirming_evidence must come from build_suggestions.yaml /
    evidence_signals.yaml regardless of what the LLM said — the LLM never supplies
    these fields, so this checks the deterministic-attachment design holds."""
    packet = build_candidate_packet(course_rag_state)
    eligible_id = packet.eligible[0].skill_id
    _patch_llm(monkeypatch, json.dumps({
        "chosen_skill_id": eligible_id,
        "alternative_skill_id": None,
        "rationale": "Some rationale.",
        "alternative_rationale": None,
    }))

    rec = build_coaching_recommendation(course_rag_state)
    assert rec.build_suggestion == _data.build_suggestion(eligible_id)
    from compass.agent.coach import _confirming_evidence
    assert rec.confirming_evidence == _confirming_evidence(eligible_id)


def test_demonstrated_panel_is_not_truncated_below_what_the_llm_saw(monkeypatch):
    """Regression test: the LLM's evidence_summary must never include a skill
    that's missing from rec.demonstrated — narrative.strengths (used by
    `profile`) is capped at 5, which previously leaked into coach mode and let
    the rationale reference skills the user was never shown."""
    state = make_state(
        [
            "rag.embeddings", "rag.chunking", "rag.retrieval_basic", "rag.hybrid", "rag.reranking",
            "eval.datasets", "eval.generation_metrics",
        ],
        repo_name="course-rag",
    )
    ai_skill_ids = set(_data.all_skill_ids())
    expected_names = [
        _data.skill_metadata()[sid]["name"]
        for sid in _demonstrated_core_skill_ids_ranked(state, ai_skill_ids)
    ]
    assert len(expected_names) > 5, "fixture must exercise more than narrative.strengths' cap of 5"

    rec = build_coaching_recommendation(state)
    assert rec.mode == "normal"
    assert rec.demonstrated == expected_names


def test_alternative_skill_name_is_attached_when_valid(course_rag_state, monkeypatch):
    packet = build_candidate_packet(course_rag_state)
    chosen_id = packet.eligible[0].skill_id
    alt_id = next(c.skill_id for c in packet.eligible if c.skill_id != chosen_id)
    _patch_llm(monkeypatch, json.dumps({
        "chosen_skill_id": chosen_id,
        "alternative_skill_id": alt_id,
        "rationale": "Main pick.",
        "alternative_rationale": "Reasonable alternative.",
    }))

    rec = build_coaching_recommendation(course_rag_state)
    assert rec.source == "llm"
    assert rec.alternative_skill_name == _data.skill_metadata()[alt_id]["name"]
    assert rec.alternative_rationale == "Reasonable alternative."
