"""Tests for `compass coach` (src/compass/agent/coach.py).

Focus: the coaching layer must never invent a skill, must defer entirely to
plan_next_milestone() for what's eligible next, and every recommendation it
produces must be traceable back to skills.yaml / evidence_signals.yaml /
build_suggestions.yaml.
"""
from __future__ import annotations

import pytest

from compass import _data
from compass.agent.coach import build_coaching_recommendation
from compass.agent.planner import plan_next_milestone

ALL_SKILL_IDS = set(_data.all_skill_ids())


def test_t_repo_refuses_with_no_evidence(t_repo_state):
    rec = build_coaching_recommendation(t_repo_state)
    assert rec.mode == "no_evidence"
    assert rec.target_skill_id is None
    assert "scan" in rec.rationale or "run" in rec.rationale


def test_itmo_recommends_an_ai_entry_point_skill(itmo_state):
    # Sanity check the fixture itself: foundation evidence only, no AI skill
    # has reached "core" strength (small foundation->AI credits can nudge a
    # score above zero without making it a demonstrated strength).
    rec = build_coaching_recommendation(itmo_state)
    assert rec.demonstrated == []
    assert rec.mode == "normal"
    assert rec.target_skill_id is not None
    assert rec.target_skill_id in ALL_SKILL_IDS

    prereqs = _data.skill_metadata()[rec.target_skill_id]["prerequisites"]
    assert prereqs == [], "with zero AI evidence, the recommended skill must be an unprerequisited entry point"


def test_course_rag_recommends_an_eligible_skill_from_planner_output(course_rag_state):
    plan = plan_next_milestone(course_rag_state)
    assert plan.top is not None, "fixture should produce a milestone candidate"

    rec = build_coaching_recommendation(course_rag_state)
    assert rec.mode == "normal"
    assert rec.target_skill_id in plan.top.skill_priorities, (
        "coach must select from the planner's eligible set for the chosen domain, "
        "not invent its own gap analysis"
    )
    assert rec.target_domain_name == plan.top.domain_name


def test_shikhu_recommends_from_its_unlocked_frontier(shikhu_state):
    plan = plan_next_milestone(shikhu_state)
    assert plan.top is not None

    rec = build_coaching_recommendation(shikhu_state)
    assert rec.mode == "normal"
    assert rec.target_skill_id in plan.top.skill_priorities


@pytest.mark.parametrize(
    "fixture_name",
    ["t_repo_state", "itmo_state", "course_rag_state", "shikhu_state"],
)
def test_no_invented_skills(fixture_name, request):
    state = request.getfixturevalue(fixture_name)
    rec = build_coaching_recommendation(state)

    if rec.target_skill_id is not None:
        assert rec.target_skill_id in ALL_SKILL_IDS

    # Every "close to next" / "demonstrated" entry must resolve to a real
    # skill name already known to skills.yaml — never a fabricated label.
    all_names = {meta["name"] for meta in _data.skill_metadata().values()}
    all_names |= {
        sub["name"]
        for dom in _data.foundation_domains()
        for sub in dom["sub_skills"]
    }
    for name in rec.demonstrated + rec.close_to_next:
        assert name in all_names


@pytest.mark.parametrize("skill_id", sorted(_data.all_skill_ids()))
def test_every_skill_maps_to_confirming_evidence(skill_id):
    """Every AI skill must have at least one detectable evidence_signals.yaml pattern —
    a recommendation for it must be falsifiable, not just a claim."""
    gh = _data.evidence_signals()["skills"].get(skill_id, {}).get("github", {})
    descriptions = [
        entry.get("description", "")
        for level in ("strong", "moderate")
        for entry in gh.get(level, [])
    ]
    assert any(descriptions), f"{skill_id} has no strong/moderate evidence_signals patterns"


@pytest.mark.parametrize("skill_id", sorted(_data.all_skill_ids()))
def test_every_skill_has_a_build_suggestion(skill_id):
    assert _data.build_suggestion(skill_id), f"{skill_id} is missing a build_suggestions.yaml entry"


def test_build_suggestions_schema_rejects_unknown_skill_id(tmp_path, monkeypatch):
    bad_yaml = tmp_path / "build_suggestions.yaml"
    bad_yaml.write_text("suggestions:\n  not.a.real.skill:\n    suggestion: invented\n")
    monkeypatch.setattr(_data, "COMPETENCY_DIR", tmp_path)
    _data._validated_build_suggestions.cache_clear()
    try:
        with pytest.raises(ValueError, match="unknown skill_id"):
            _data._validated_build_suggestions()
    finally:
        _data._validated_build_suggestions.cache_clear()


def test_build_suggestions_schema_rejects_empty_suggestion(tmp_path, monkeypatch):
    bad_yaml = tmp_path / "build_suggestions.yaml"
    bad_yaml.write_text("suggestions:\n  prompting.basic:\n    suggestion: ''\n")
    monkeypatch.setattr(_data, "COMPETENCY_DIR", tmp_path)
    _data._validated_build_suggestions.cache_clear()
    try:
        with pytest.raises(ValueError, match="missing a non-empty"):
            _data._validated_build_suggestions()
    finally:
        _data._validated_build_suggestions.cache_clear()
