"""Pydantic models for all learner state."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


Background = Literal["product_manager", "software_engineer", "data_scientist", "ml_engineer"]
TargetRole = Literal["ai_engineer", "ai_builder"]
DesiredDepth = Literal["awareness", "practitioner", "expert"]
LearningStyle = Literal["build_first", "concept_first", "balanced"]
SkillConfidence = Literal["low", "medium", "high"]
MilestoneState = Literal["not_started", "in_progress", "demonstrated", "reinforced"]
ProjectSize = Literal["micro", "standard", "extended"]
OverrideType = Literal[
    "already_know", "not_interested", "want_deeper",
    "focus_lock", "mark_complete", "resize_project",
]


class LearnerProfile(BaseModel):
    learner_id: str = Field(default_factory=_uuid)
    name: str
    github_username: Optional[str] = None
    background: Background
    target_role: TargetRole = "ai_engineer"
    desired_depth: DesiredDepth
    learning_style: LearningStyle
    created_at: datetime = Field(default_factory=_now)


class SkillEvidence(BaseModel):
    evidence_id: str = Field(default_factory=_uuid)
    skill_id: str
    evidence_type: Literal["observed", "inferred", "synthesized"]
    recency: Literal["current", "historical", "unknown"]
    confidence: int  # 0–100
    source_repo: Optional[str] = None
    source_path: Optional[str] = None
    source: Literal["scan", "llm"] = "scan"  # provenance — corrections from `compass review` only ever target "llm"
    matched_signals: list[str] = Field(default_factory=list)  # human-readable pattern descriptions (scan-sourced only)
    rationale: str = ""
    recorded_at: datetime = Field(default_factory=_now)

    @property
    def level(self) -> str:
        if self.confidence >= 70:
            return "strong"
        if self.confidence >= 40:
            return "moderate"
        return "weak"


class SkillScore(BaseModel):
    skill_id: str
    current_score: float = 0.0    # aggregated from evidence, penalises historical/inferred
    experience_score: float = 0.0 # aggregated with generous historical/inferred weights
    base_score: float = 0.0       # role prior — set on init, never changes
    confidence: SkillConfidence = "low"
    last_updated: datetime = Field(default_factory=_now)
    evidence_sources: list[str] = Field(default_factory=list)
    is_override: bool = False

    @property
    def effective_score(self) -> float:
        return min(1.0, self.current_score + self.base_score)


class ParsedSignal(BaseModel):
    skill_id: str
    signal_type: str  # github_strong | github_moderate | github_weak | journal_*
    source: str       # file path, repo name, or journal entry id
    weight: float


class OverrideIntent(BaseModel):
    type: OverrideType
    target: str       # skill_id or domain
    requires_confirmation: bool = True


class JournalEntry(BaseModel):
    entry_id: str = Field(default_factory=_uuid)
    date: datetime = Field(default_factory=_now)
    raw_text: str
    parsed_signals: list[ParsedSignal] = Field(default_factory=list)
    override_intents: list[OverrideIntent] = Field(default_factory=list)


class Override(BaseModel):
    override_id: str = Field(default_factory=_uuid)
    type: OverrideType
    target: str
    applied_at: datetime = Field(default_factory=_now)
    source: str = "user"
    expires_at: Optional[datetime] = None


class ProjectRecommendation(BaseModel):
    title: str
    goal: str
    size: ProjectSize
    suggested_start: Optional[str] = None
    deliverables: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    exploration_phase: Optional[str] = None


class Milestone(BaseModel):
    milestone_id: str = Field(default_factory=_uuid)
    domain: str
    title: str
    target_skills: list[str] = Field(default_factory=list)
    state: MilestoneState = "not_started"
    rationale: str = ""
    success_criteria: list[str] = Field(default_factory=list)
    project: Optional[ProjectRecommendation] = None
    created_at: datetime = Field(default_factory=_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class LLMSkillAssessment(BaseModel):
    skill_id: str
    confidence: float
    evidence_type: Literal[
        "current_demonstrated",
        "historical_experience",
        "inferred_exposure",
        "inferred_low_confidence",  # downgraded: rationale lacks concrete evidence
    ]
    rationale: str
    needs_review: bool = False      # high LLM confidence but zero deterministic evidence
    review_reason: str = ""         # explains why needs_review or inferred_low_confidence


class LLMRepoAssessment(BaseModel):
    repo_name: str
    assessed_at: datetime = Field(default_factory=_now)
    skills: list[LLMSkillAssessment] = Field(default_factory=list)
    repo_summary: str = ""
    repo_recency: Literal["current", "historical", "unknown"] = "unknown"
    model: str = ""
    error: Optional[str] = None


class ToolCallRecord(BaseModel):
    step: str                                  # tool/step name, e.g. "repo_scan"
    started_at: datetime = Field(default_factory=_now)
    duration_ms: int = 0
    inputs: dict = Field(default_factory=dict)   # summarized inputs, not full payloads
    outputs: dict = Field(default_factory=dict)  # summarized outputs
    error: Optional[str] = None


class DivergenceFlag(BaseModel):
    skill_id: str
    llm_confidence: float
    deterministic_score: float
    reason: str
    resolved: bool = False
    correction_id: Optional[str] = None


CorrectionAction = Literal["accept", "downgrade", "reject", "correct"]


class EvidenceCorrection(BaseModel):
    """A user decision from `compass review`, applied as a transform at aggregation
    time. Keyed by (skill_id, source_repo) so it survives repo rescans even though
    individual SkillEvidence records are replaced on every scan/analyze pass.
    source_repo=None means the correction applies to this skill everywhere.
    """
    correction_id: str = Field(default_factory=_uuid)
    skill_id: str
    source_repo: Optional[str] = None
    action: CorrectionAction
    corrected_skill_id: Optional[str] = None
    corrected_recency: Optional[str] = None
    corrected_evidence_type: Optional[str] = None
    note: str = ""
    run_id: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class SkillAggregationTrace(BaseModel):
    skill_id: str
    contributions: list[dict] = Field(default_factory=list)  # per-record breakdown
    current_score: float = 0.0
    experience_score: float = 0.0


class RunTrace(BaseModel):
    run_id: str = Field(default_factory=_uuid)
    learner_id: str
    repo_name: str
    repo_path: str
    started_at: datetime = Field(default_factory=_now)
    completed_at: Optional[datetime] = None
    steps: list[ToolCallRecord] = Field(default_factory=list)
    files_sampled: list[str] = Field(default_factory=list)
    llm_prompt: str = ""
    llm_response: str = ""
    evidence_created: list[SkillEvidence] = Field(default_factory=list)
    divergence_flags: list[DivergenceFlag] = Field(default_factory=list)
    aggregation: list[SkillAggregationTrace] = Field(default_factory=list)
    recommendation_summary: dict = Field(default_factory=dict)


class GitHubCache(BaseModel):
    last_scan: datetime = Field(default_factory=_now)
    repos: list[str] = Field(default_factory=list)
    repo_chronology: dict[str, dict[str, Optional[str]]] = Field(default_factory=dict)  # repo_name -> {"first_commit_date", "last_commit_date"}
    latest_signals: list[ParsedSignal] = Field(default_factory=list)
    files_scanned: int = 0
    scan_errors: list[str] = Field(default_factory=list)


class CurriculumResource(BaseModel):
    url: str
    title: str
    resource_type: str
    relevance_note: str = ""
    sequence_position: int = 1
    credibility_score: float = 0.65


class ConceptSection(BaseModel):
    concept: str
    explanation: str
    why_it_matters: str


class ModuleAdjustment(BaseModel):
    type: Literal["remove_resource", "depth_change", "format_filter", "refresh"]
    detail: str
    applied_at: datetime = Field(default_factory=_now)


class CurriculumModule(BaseModel):
    module_id: str = Field(default_factory=_uuid)
    milestone_id: str
    title: str
    duration_estimate: str = ""
    learning_objectives: list[str] = Field(default_factory=list)
    concept_primer: list[ConceptSection] = Field(default_factory=list)
    resources: list[CurriculumResource] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_now)
    resource_search_date: datetime = Field(default_factory=_now)
    failure_mode: Optional[Literal["minimal"]] = None
    user_adjustments: list[ModuleAdjustment] = Field(default_factory=list)


class LearnerState(BaseModel):
    profile: LearnerProfile
    evidence: list[SkillEvidence] = Field(default_factory=list)
    skill_graph: dict[str, SkillScore] = Field(default_factory=dict)
    active_milestone: Optional[Milestone] = None
    completed_milestones: list[Milestone] = Field(default_factory=list)
    journal_entries: list[JournalEntry] = Field(default_factory=list)
    github_cache: Optional[GitHubCache] = None
    overrides: list[Override] = Field(default_factory=list)
    modules: dict[str, CurriculumModule] = Field(default_factory=dict)
    llm_assessments: list[LLMRepoAssessment] = Field(default_factory=list)
    corrections: list[EvidenceCorrection] = Field(default_factory=list)

    @property
    def is_new_learner(self) -> bool:
        return self.github_cache is None and len(self.journal_entries) == 0
