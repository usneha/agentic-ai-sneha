"""Pydantic models for the learner-centered coaching path.

Distinct from compass/models.py's LearnerState/skill_graph — that path stays
untouched. This path's primary artifact is a LearnerCoachProfile built from
LLM beliefs about the learner, grounded by construction: every belief/claim
that cites evidence must cite it by EvidenceItem id, never a free-form quote,
so a validator can check the citation actually exists.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from ..models import _now, _uuid

EvidenceSourceType = Literal["github_repo", "doc", "blog", "reflection"]
AssessmentSource = Literal["llm", "deterministic_fallback"]


def _evidence_id() -> str:
    return f"ev_{uuid.uuid4().hex[:8]}"


class EvidenceItem(BaseModel):
    id: str = Field(default_factory=_evidence_id)
    source_id: str
    source_type: EvidenceSourceType
    artifact_path: Optional[str] = None
    quote: Optional[str] = None
    summary: str
    metadata: dict = Field(default_factory=dict)


class EvidenceSource(BaseModel):
    source_id: str = Field(default_factory=_uuid)
    source_type: EvidenceSourceType
    source_name: str
    collected_at: datetime = Field(default_factory=_now)
    items: list[EvidenceItem] = Field(default_factory=list)


# ── Coach assessment (one run's diagnosis, not persisted as profile state) ────

class CapabilityClaim(BaseModel):
    capability: str
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)
    why_it_matters: str = ""


class GapClaim(BaseModel):
    gap: str
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)
    why_it_matters: str = ""


class UncertaintyClaim(BaseModel):
    uncertainty: str
    missing_evidence: list[str] = Field(default_factory=list)
    how_to_test: str = ""


class CoachAssessment(BaseModel):
    current_stage: str
    demonstrated_capabilities: list[CapabilityClaim] = Field(default_factory=list)
    growth_gaps: list[GapClaim] = Field(default_factory=list)
    uncertainties: list[UncertaintyClaim] = Field(default_factory=list)
    learning_style_observations: list[str] = Field(default_factory=list)
    coach_summary: str = ""
    source: AssessmentSource = "llm"
    fallback_reason: Optional[str] = None


# ── Persisted learner profile ──────────────────────────────────────────────

class Strength(BaseModel):
    strength: str
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)


class GrowthEdge(BaseModel):
    growth_edge: str
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)


class CoachBelief(BaseModel):
    belief: str
    confidence: float
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    could_be_disproven_by: Optional[str] = None


class LearnerCoachProfile(BaseModel):
    learner_id: str
    goals: list[str] = Field(default_factory=list)
    project_history: list[str] = Field(default_factory=list)
    strengths: list[Strength] = Field(default_factory=list)
    growth_edges: list[GrowthEdge] = Field(default_factory=list)
    uncertainties: list[UncertaintyClaim] = Field(default_factory=list)
    learning_style: list[str] = Field(default_factory=list)
    builder_patterns: list[str] = Field(default_factory=list)
    coach_beliefs: list[CoachBelief] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=_now)


# ── Coaching recommendation ──────────────────────────────────────────────────

class BuildSpec(BaseModel):
    project_goal: str
    required_capabilities: list[str] = Field(default_factory=list)
    suggested_artifacts: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class CoachingRecommendation(BaseModel):
    next_challenge: str
    why_this: str
    targeted_growth_edges: list[str] = Field(default_factory=list)
    build_spec: BuildSpec
    success_criteria: list[str] = Field(default_factory=list)
    evidence_compass_will_look_for: list[str] = Field(default_factory=list)
    coach_note: str = ""
    source: AssessmentSource = "llm"
    fallback_reason: Optional[str] = None


# ── Episodic history ──────────────────────────────────────────────────────────

class CoachingCycle(BaseModel):
    """One full run of assess -> update_profile -> recommend. Cycles are
    appended, never overwritten, so the coach can be asked what it believed
    at any prior point, not just what it believes now."""
    cycle_id: str = Field(default_factory=_uuid)
    ran_at: datetime = Field(default_factory=_now)
    evidence_count: int = 0
    assessment: CoachAssessment
    recommendation: CoachingRecommendation


# ── Top-level persisted state ────────────────────────────────────────────────

class LearnerCoachState(BaseModel):
    profile: LearnerCoachProfile
    evidence_sources: list[EvidenceSource] = Field(default_factory=list)
    history: list[CoachingCycle] = Field(default_factory=list)

    @property
    def latest_cycle(self) -> Optional[CoachingCycle]:
        return self.history[-1] if self.history else None
