"""Prompt builders for the three learner-coach LLM calls.

Shared evidence-grounding rule across all three: list evidence by id, and
require any citation to use only those ids. The LLM never sees a path to
free-form quote/evidence text in the output schema, so there is nothing to
fabricate there — validation.py still strips any id that isn't real.
"""
from __future__ import annotations

from .models import CoachAssessment, EvidenceItem, LearnerCoachProfile

_GROUNDING_RULE = """Evidence grounding rule (hard requirement):
When citing evidence, use only the evidence ids listed below — values like
"ev_xxxxxxxx". Do not invent ids, quotes, or file paths. If a claim has no
real evidence to cite, do not make the claim."""


def _format_evidence(evidence: list[EvidenceItem]) -> str:
    if not evidence:
        return "(no evidence collected yet)"
    lines = []
    for item in evidence:
        loc = f" ({item.artifact_path})" if item.artifact_path else ""
        quote = f' — "{item.quote}"' if item.quote else ""
        lines.append(f"- id={item.id} [{item.source_type}/{item.source_id}]{loc}: {item.summary}{quote}")
    return "\n".join(lines)


def _format_profile(profile: LearnerCoachProfile) -> str:
    return f"""learner_id: {profile.learner_id}
goals: {profile.goals or '(none stated)'}
project_history: {profile.project_history or '(none)'}
current strengths: {[s.strength for s in profile.strengths] or '(none yet)'}
current growth_edges: {[g.growth_edge for g in profile.growth_edges] or '(none yet)'}
current uncertainties: {[u.uncertainty for u in profile.uncertainties] or '(none yet)'}
learning_style: {profile.learning_style or '(not yet observed)'}
builder_patterns: {profile.builder_patterns or '(not yet observed)'}
coach_beliefs: {[b.belief for b in profile.coach_beliefs] or '(none yet)'}"""


def build_assessment_prompt(profile: LearnerCoachProfile, evidence: list[EvidenceItem]) -> str:
    return f"""You are Compass, an AI learning coach.

The learner is the unit of analysis. Repositories, documents, blogs, and
reflections are evidence sources only — never treat any single one of them
as the learner's complete profile.

EXISTING LEARNER PROFILE:
{_format_profile(profile)}

EVIDENCE (cite only these ids):
{_format_evidence(evidence)}

Your task is to determine what this evidence shows about the learner. Think
like an experienced mentor evaluating capability, systems thinking, decision
making, tradeoff reasoning, execution quality, learning patterns, and
uncertainty. Do not produce a flat skill inventory or mechanically map
technologies to skills.

{_GROUNDING_RULE}

Return ONLY valid JSON, no markdown fences:
{{
  "current_stage": "string",
  "demonstrated_capabilities": [
    {{"capability": "string", "confidence": 0.0, "evidence_ids": ["ev_..."], "why_it_matters": "string"}}
  ],
  "growth_gaps": [
    {{"gap": "string", "confidence": 0.0, "evidence_ids": ["ev_..."], "why_it_matters": "string"}}
  ],
  "uncertainties": [
    {{"uncertainty": "string", "missing_evidence": ["string"], "how_to_test": "string"}}
  ],
  "learning_style_observations": ["string"],
  "coach_summary": "string"
}}"""


def build_profile_update_prompt(
    profile: LearnerCoachProfile,
    evidence: list[EvidenceItem],
    assessment: CoachAssessment,
) -> str:
    return f"""You are updating a living learner profile.

The learner is the unit of analysis. Evidence sources are observations, not
the profile itself.

PREVIOUS LEARNER PROFILE:
{_format_profile(profile)}

EVIDENCE (cite only these ids):
{_format_evidence(evidence)}

LATEST COACH ASSESSMENT:
current_stage: {assessment.current_stage}
demonstrated_capabilities: {[c.capability for c in assessment.demonstrated_capabilities]}
growth_gaps: {[g.gap for g in assessment.growth_gaps]}
uncertainties: {[u.uncertainty for u in assessment.uncertainties]}
coach_summary: {assessment.coach_summary}

Rules:
- Preserve useful prior knowledge; only add new beliefs when supported by evidence.
- Lower confidence when evidence is weak or contradictory.
- Track uncertainty explicitly.
- Do not collapse the profile into a skill list. Model the learner, not the repositories.

{_GROUNDING_RULE}

Return ONLY valid JSON, no markdown fences:
{{
  "goals": ["string"],
  "project_history": ["string"],
  "strengths": [
    {{"strength": "string", "confidence": 0.0, "evidence_ids": ["ev_..."]}}
  ],
  "growth_edges": [
    {{"growth_edge": "string", "confidence": 0.0, "evidence_ids": ["ev_..."]}}
  ],
  "uncertainties": [
    {{"uncertainty": "string", "missing_evidence": ["string"], "how_to_test": "string"}}
  ],
  "learning_style": ["string"],
  "builder_patterns": ["string"],
  "coach_beliefs": [
    {{
      "belief": "string",
      "confidence": 0.0,
      "supporting_evidence_ids": ["ev_..."],
      "missing_evidence": ["string"],
      "could_be_disproven_by": "string"
    }}
  ]
}}"""


def build_recommendation_prompt(profile: LearnerCoachProfile, assessment: CoachAssessment) -> str:
    return f"""You are Compass, an AI learning coach.

UPDATED LEARNER PROFILE:
{_format_profile(profile)}

LATEST COACH ASSESSMENT:
current_stage: {assessment.current_stage}
demonstrated_capabilities: {[c.capability for c in assessment.demonstrated_capabilities]}
growth_gaps: {[g.gap for g in assessment.growth_gaps]}
uncertainties: {[u.uncertainty for u in assessment.uncertainties]}
coach_summary: {assessment.coach_summary}

Recommend the single highest-leverage next challenge. This is a coaching
decision, not a skill-taxonomy lookup or a rules-engine decision. The
challenge must support the learner's goals, build on demonstrated strengths,
target meaningful growth edges, reduce uncertainty, and create observable
evidence. Avoid generic courses, static skill progression maps, or
keyword-driven recommendations.

Return ONLY valid JSON, no markdown fences:
{{
  "next_challenge": "string",
  "why_this": "string",
  "targeted_growth_edges": ["string"],
  "build_spec": {{
    "project_goal": "string",
    "required_capabilities": ["string"],
    "suggested_artifacts": ["string"],
    "constraints": ["string"]
  }},
  "success_criteria": ["string"],
  "evidence_compass_will_look_for": ["string"],
  "coach_note": "string"
}}"""
