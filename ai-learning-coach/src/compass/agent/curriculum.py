"""Curriculum module generator.

Uses the Anthropic API to generate a focused learning module for the active
milestone. Falls back to a minimal (resources-only) module if the LLM call
fails after retries.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import openai

from ..config import OPENAI_API_KEY, OPENAI_MODEL
from ..models import (
    ConceptSection,
    CurriculumModule,
    CurriculumResource,
    LearnerState,
    Milestone,
)


@dataclass
class ModuleResult:
    module: CurriculumModule
    failure_mode: str | None  # None = full module; "minimal" = resources only


_DEPTH_GUIDANCE = {
    "awareness": "Keep explanations accessible. Emphasize what the concept does and why it matters. No deep implementation detail.",
    "practitioner": "Include practical implementation context. Balance concept explanation with hands-on application.",
    "expert": "Include production patterns, edge cases, trade-offs, and advanced techniques.",
}

_BACKGROUND_GUIDANCE = {
    "software_engineer": "Frame concepts in terms of system design, APIs, and engineering trade-offs.",
    "data_scientist": "Connect to experimentation, evaluation, and statistical thinking you already have.",
    "ml_engineer": "Relate to model development, infrastructure, and production ML patterns you know well.",
    "product_manager": "Emphasize outcomes, decision-making levers, and how to evaluate AI capabilities.",
}

_STATIC_RESOURCES: dict[str, list[dict]] = {
    "prompting": [
        {"url": "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview", "title": "Anthropic Prompt Engineering Guide", "resource_type": "docs", "credibility_score": 0.95},
        {"url": "https://platform.openai.com/docs/guides/prompt-engineering", "title": "OpenAI Prompt Engineering Guide", "resource_type": "docs", "credibility_score": 0.90},
        {"url": "https://www.promptingguide.ai", "title": "Prompting Guide (DAIR.AI)", "resource_type": "tutorial", "credibility_score": 0.80},
    ],
    "rag": [
        {"url": "https://python.langchain.com/docs/tutorials/rag/", "title": "LangChain RAG Tutorial", "resource_type": "tutorial", "credibility_score": 0.85},
        {"url": "https://docs.llamaindex.ai/en/stable/getting_started/concepts.html", "title": "LlamaIndex RAG Concepts", "resource_type": "docs", "credibility_score": 0.85},
        {"url": "https://huggingface.co/learn/cookbook/rag_with_hugging_face_gemma_mongodb", "title": "HuggingFace RAG Cookbook", "resource_type": "tutorial", "credibility_score": 0.80},
    ],
    "eval": [
        {"url": "https://docs.smith.langchain.com/evaluation", "title": "LangSmith Evaluation Docs", "resource_type": "docs", "credibility_score": 0.85},
        {"url": "https://docs.ragas.io/en/latest/getstarted/", "title": "RAGAS Getting Started", "resource_type": "docs", "credibility_score": 0.80},
        {"url": "https://www.deepeval.com/docs", "title": "DeepEval Documentation", "resource_type": "docs", "credibility_score": 0.80},
    ],
    "agents": [
        {"url": "https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview", "title": "Anthropic Tool Use Guide", "resource_type": "docs", "credibility_score": 0.95},
        {"url": "https://python.langchain.com/docs/tutorials/agents/", "title": "LangChain Agents Tutorial", "resource_type": "tutorial", "credibility_score": 0.85},
        {"url": "https://docs.anthropic.com/en/docs/agents-and-tools/agents/overview", "title": "Anthropic Agent Patterns", "resource_type": "docs", "credibility_score": 0.95},
    ],
    "memory": [
        {"url": "https://python.langchain.com/docs/concepts/memory/", "title": "LangChain Memory Concepts", "resource_type": "docs", "credibility_score": 0.85},
        {"url": "https://docs.anthropic.com/en/docs/agents-and-tools/agents/memory", "title": "Anthropic Memory Patterns", "resource_type": "docs", "credibility_score": 0.90},
    ],
    "mcp": [
        {"url": "https://modelcontextprotocol.io/introduction", "title": "MCP Official Introduction", "resource_type": "docs", "credibility_score": 0.95},
        {"url": "https://modelcontextprotocol.io/quickstart/server", "title": "MCP Server Quickstart", "resource_type": "tutorial", "credibility_score": 0.95},
    ],
    "deployment": [
        {"url": "https://docs.anthropic.com/en/api/getting-started", "title": "Anthropic API Reference", "resource_type": "docs", "credibility_score": 0.95},
        {"url": "https://fastapi.tiangolo.com/", "title": "FastAPI Documentation", "resource_type": "docs", "credibility_score": 0.90},
    ],
    "observability": [
        {"url": "https://docs.smith.langchain.com/", "title": "LangSmith Documentation", "resource_type": "docs", "credibility_score": 0.90},
        {"url": "https://docs.arize.com/arize/llm-large-language-models", "title": "Arize AI LLM Observability", "resource_type": "docs", "credibility_score": 0.80},
    ],
}


def _build_prompt(state: LearnerState, milestone: Milestone) -> str:
    p = state.profile
    depth_guidance = _DEPTH_GUIDANCE.get(p.desired_depth, "")
    bg_guidance = _BACKGROUND_GUIDANCE.get(p.background, "")

    skills_str = ", ".join(milestone.target_skills)
    skill_scores = {
        sid: state.skill_graph[sid].score
        for sid in milestone.target_skills
        if sid in state.skill_graph
    }
    scores_str = "\n".join(f"  - {sid}: {v:.2f}" for sid, v in skill_scores.items())

    return f"""You are generating a personalized learning module for an AI Builder Compass learner.

LEARNER PROFILE:
- Name: {p.name}
- Background: {p.background}
- Target depth: {p.desired_depth}
- Learning style: {p.learning_style}
- Background guidance: {bg_guidance}
- Depth guidance: {depth_guidance}

MILESTONE:
- Domain: {milestone.domain}
- Title: {milestone.title}
- Target skills: {skills_str}
- Current skill scores (0.0–1.0, target is {state.profile.desired_depth}):
{scores_str}

Generate a focused learning module for this milestone. Return a JSON object with exactly this structure:

{{
  "title": "string — specific, engaging module title",
  "duration_estimate": "string — realistic time range (e.g. '4–6 hours')",
  "learning_objectives": ["string", ...],  // 3–5 concrete, measurable objectives
  "concept_primer": [
    {{
      "concept": "string — concept name",
      "explanation": "string — 2–4 sentences tailored to this learner's background",
      "why_it_matters": "string — 1–2 sentences on why this matters now for this learner"
    }},
    ...
  ],  // 2–4 key concepts
  "resources": [
    {{
      "url": "string — real, valid URL",
      "title": "string — resource title",
      "resource_type": "docs | tutorial | video | course | paper",
      "relevance_note": "string — why this resource fits this learner at this depth",
      "sequence_position": integer  // 1-indexed
    }},
    ...
  ],  // 3–5 curated resources (real URLs only)
  "suggested_project": "string — 2–3 sentences describing a concrete project to build",
  "success_criteria": ["string", ...],  // 3–4 checkable criteria
  "reflection_questions": ["string", ...]  // 2–3 questions to deepen understanding
}}

Critical constraints:
- Only include real URLs that you are confident exist
- Tailor explanations to the learner's {p.background} background
- Keep the module focused on the gap between current scores and {p.desired_depth} level
- Prefer official documentation and well-known learning resources
- Return ONLY the JSON object, no markdown fences or extra text"""


def generate_module(state: LearnerState, milestone: Milestone, max_retries: int = 2) -> ModuleResult:
    """Generate a curriculum module using the LLM.

    Returns a full module on success, or a minimal (resources-only) module after
    exhausting retries.
    """
    if not OPENAI_API_KEY:
        return _minimal_module(milestone, reason="no_api_key")

    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    prompt = _build_prompt(state, milestone)

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.choices[0].message.content.strip()
            # Strip markdown fences if the model added them
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            return _build_module(milestone, data)
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            if attempt == max_retries:
                return _minimal_module(milestone, reason=f"parse_error: {exc}")
        except openai.OpenAIError as exc:
            if attempt == max_retries:
                return _minimal_module(milestone, reason=f"api_error: {exc}")

    return _minimal_module(milestone, reason="exhausted")


def _build_module(milestone: Milestone, data: dict) -> ModuleResult:
    concepts = [
        ConceptSection(
            concept=c["concept"],
            explanation=c["explanation"],
            why_it_matters=c["why_it_matters"],
        )
        for c in data.get("concept_primer", [])
    ]
    resources = [
        CurriculumResource(
            url=r["url"],
            title=r["title"],
            resource_type=r.get("resource_type", "docs"),
            relevance_note=r.get("relevance_note", ""),
            sequence_position=r.get("sequence_position", i + 1),
            credibility_score=0.75,
        )
        for i, r in enumerate(data.get("resources", []))
    ]
    # Merge in success criteria and reflection questions as extra fields
    success_criteria = data.get("success_criteria", milestone.success_criteria)
    # Store suggested_project and reflections in the first concept's why_it_matters
    # if not already captured (simple MVP approach)
    if data.get("suggested_project") and concepts:
        concepts[-1].why_it_matters += f"\n\nSuggested project: {data['suggested_project']}"

    module = CurriculumModule(
        milestone_id=milestone.milestone_id,
        title=data.get("title", milestone.title),
        duration_estimate=data.get("duration_estimate", ""),
        learning_objectives=data.get("learning_objectives", []),
        concept_primer=concepts,
        resources=resources,
        failure_mode=None,
    )
    return ModuleResult(module=module, failure_mode=None)


def _minimal_module(milestone: Milestone, reason: str = "") -> ModuleResult:
    """Return a resources-only module when LLM generation fails."""
    domain = milestone.domain
    static = _STATIC_RESOURCES.get(domain, _STATIC_RESOURCES.get("prompting", []))
    resources = [
        CurriculumResource(
            url=r["url"],
            title=r["title"],
            resource_type=r.get("resource_type", "docs"),
            relevance_note="Curated fallback resource",
            sequence_position=i + 1,
            credibility_score=r.get("credibility_score", 0.65),
        )
        for i, r in enumerate(static)
    ]
    module = CurriculumModule(
        milestone_id=milestone.milestone_id,
        title=milestone.title,
        duration_estimate="",
        learning_objectives=[],
        concept_primer=[],
        resources=resources,
        failure_mode="minimal",
    )
    return ModuleResult(module=module, failure_mode=reason)
