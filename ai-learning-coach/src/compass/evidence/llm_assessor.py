"""LLM-based repo skill assessment — Layer 2 evidence.

Reads README + file tree + sampled files, asks an LLM to assess which
skills are evidenced, and returns structured assessments per skill.

Output is stored separately from deterministic signals (llm_assessments
on LearnerState) and does NOT affect skill graph scores. Exposed via
`compass explain`.

Guardrails (applied via apply_guardrails() before saving):
  - Divergence: LLM confidence >= 0.7 with deterministic score == 0.0
    → flagged needs_review=True; signal preserved but visually marked
  - Evidence quality: rationale lacks a concrete reference (file path,
    class/function name, package, quoted phrase)
    → evidence_type downgraded to inferred_low_confidence

See scanner.py docstring for the full three-layer architecture note.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import openai

from .._data import foundation_domains, skill_metadata
from ..config import OPENAI_API_KEY, OPENAI_MODEL
from ..models import LLMRepoAssessment, LLMSkillAssessment

MAX_README_CHARS = 3_000
MAX_FILE_CHARS = 1_500
MAX_FILES_SAMPLED = 5

_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    "jquery", "vendor", "bower_components", "lib", "libs",
    "static", "public", "dist", "build", "submission", "output",
    "data", "docs/_build", "coverage", "htmlcov",
})

_SKIP_SUFFIXES = frozenset({
    ".min.js", ".min.css", ".bundle.js", ".lock",
    ".pb", ".onnx", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".pdf",
})

_PRIORITY_NAMES = frozenset({
    "main.py", "app.py", "index.py", "server.py", "api.py",
    "index.js", "server.js", "app.js", "index.ts", "app.ts",
    "index.php", "app.php",
    "pyproject.toml", "package.json", "Dockerfile", "docker-compose.yml",
})


# ── Context assembly ──────────────────────────────────────────────────────────

def _read_readme(repo_path: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt", "README"):
        p = repo_path / name
        if p.exists():
            return p.read_text(encoding="utf-8", errors="ignore")[:MAX_README_CHARS]
    return ""


def _file_tree(repo_path: Path) -> str:
    lines: list[str] = []
    for item in sorted(repo_path.iterdir()):
        if item.name.startswith(".") or item.name in _SKIP_DIRS:
            continue
        lines.append(item.name + ("/" if item.is_dir() else ""))
        if item.is_dir():
            try:
                for sub in sorted(item.iterdir())[:20]:
                    if not sub.name.startswith(".") and sub.name not in _SKIP_DIRS:
                        lines.append(f"  {sub.name}" + ("/" if sub.is_dir() else ""))
            except PermissionError:
                pass
    return "\n".join(lines)


def _sample_files(repo_path: Path) -> list[dict]:
    candidates: list[Path] = []
    for path in sorted(repo_path.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(repo_path).parts
        if any(p in _SKIP_DIRS or (p.startswith(".") and p not in {".env.example"}) for p in parts[:-1]):
            continue
        name_lower = path.name.lower()
        if any(name_lower.endswith(s) for s in _SKIP_SUFFIXES):
            continue
        candidates.append(path)

    priority = [p for p in candidates if p.name in _PRIORITY_NAMES]
    others = sorted(
        [p for p in candidates if p.name not in _PRIORITY_NAMES],
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    sampled = (priority + others)[:MAX_FILES_SAMPLED]

    result = []
    for p in sampled:
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")[:MAX_FILE_CHARS]
            result.append({"path": str(p.relative_to(repo_path)), "content": content})
        except OSError:
            pass
    return result


def _build_context(repo_path: Path) -> dict:
    return {
        "readme": _read_readme(repo_path),
        "tree": _file_tree(repo_path),
        "files": _sample_files(repo_path),
    }


# ── Prompt ────────────────────────────────────────────────────────────────────

def _skill_taxonomy() -> str:
    lines = ["AI Skills:"]
    current_domain = None
    for skill_id, info in skill_metadata().items():
        if info["domain"] != current_domain:
            lines.append(f"  [{info['domain']}]")
            current_domain = info["domain"]
        lines.append(f"    {skill_id}: {info['name']}")
    lines.append("\nFoundation Skills:")
    for fdom in foundation_domains():
        for sub in fdom["sub_skills"]:
            lines.append(f"    {sub['id']}: {sub['name']}")
    return "\n".join(lines)


def _build_prompt(repo_name: str, ctx: dict) -> str:
    files_str = "".join(
        f"\n--- {f['path']} ---\n{f['content']}\n" for f in ctx["files"]
    )
    return f"""You are assessing a software repository to determine which skills its author has demonstrated.

Repository: {repo_name}

FILE TREE:
{ctx['tree']}

README:
{ctx['readme'] or '(none)'}

SAMPLED FILES:{files_str or ' (none)'}

SKILL TAXONOMY:
{_skill_taxonomy()}

Task: assess which skills from the taxonomy are evidenced by this repository.

For each evidenced skill, return:
- skill_id: must match taxonomy exactly
- confidence: 0.0–1.0
- evidence_type:
    current_demonstrated  — hands-on implementation, likely recent
    historical_experience — evidence the skill was used but patterns appear dated (>2 years old tooling, deprecated APIs, old framework versions)
    inferred_exposure     — person likely encountered this to build what's here, but didn't directly implement it
- rationale: 1–2 sentences citing specific evidence in the repo

Rules:
- Only include skills you can point to concrete evidence for
- Do NOT infer skills just because the domain is adjacent
- Prefer 5 specific skills over 20 guesses
- inferred_exposure confidence must be < 0.5
- Set historical_experience when you see clear markers of age (e.g. PHP 5 style, jQuery 1.x, Python 2, deprecated AWS SDK v1 patterns)

Also classify repo_recency:
- "current"    — modern library versions (2022+), recent dates in code/docs, up-to-date APIs
- "historical" — dated patterns: PHP 5 style, jQuery 1.x, Python 2, deprecated SDKs, pre-2020 tooling
- "unknown"    — cannot determine from available context

Also write repo_summary: 2–3 sentences on what the repo does, its tech stack, and approximate maturity/age.

Return ONLY valid JSON, no markdown fences:
{{
  "repo_summary": "string",
  "repo_recency": "current",
  "skills": [
    {{"skill_id": "string", "confidence": 0.0, "evidence_type": "string", "rationale": "string"}}
  ]
}}"""


# ── Guardrails ────────────────────────────────────────────────────────────────

# Patterns that indicate a rationale contains a concrete evidence reference.
_CONCRETE_PATTERNS = [
    r'\b\w[\w/]*\.\w{2,4}\b',          # filename.ext or path/to/file.ext
    r'[A-Z][a-z]+[A-Z]\w*[\(\[]',      # CamelCase class/function call
    r'[a-z_]{3,}\s*[\(\[]',            # snake_case function call
    r'\$[A-Za-z_]\w+',                 # PHP/shell variable
    r'`[^`]{3,}`',                     # backtick-quoted code
    r"'[A-Za-z][\w/.-]{3,}'",          # quoted identifier/path
    r'"[A-Za-z][\w/.-]{3,}"',          # quoted identifier/path
    r'\b(import|require|use|from)\s+\w[\w.\\]+',  # import statement
    r'\b(boto3|openai|langchain|fastapi|flask|express|django|rails|'
    r'jquery|axios|aws|s3|ec2|rds|sns|docker|pytest|jest|phpunit)\b',
]
_CONCRETE_RE = re.compile("|".join(_CONCRETE_PATTERNS), re.IGNORECASE)

_DIVERGENCE_THRESHOLD = 0.70   # LLM confidence at or above this
_DIVERGENCE_DET_MAX   = 0.00   # with deterministic score at or below this


def _has_concrete_evidence(rationale: str) -> bool:
    """Return True if rationale contains a specific, citable evidence reference."""
    return len(rationale) >= 40 and bool(_CONCRETE_RE.search(rationale))


def apply_guardrails(
    assessment: LLMRepoAssessment,
    skill_graph: dict,
) -> LLMRepoAssessment:
    """Apply divergence and evidence-quality guardrails in place.

    Mutates assessment.skills entries — does not remove any signals.
    """
    for skill in assessment.skills:
        # 1. Divergence guardrail
        det = skill_graph.get(skill.skill_id)
        det_score = det.effective_score if det else 0.0
        if skill.confidence >= _DIVERGENCE_THRESHOLD and det_score <= _DIVERGENCE_DET_MAX:
            skill.needs_review = True
            skill.review_reason = (
                f"LLM confidence {skill.confidence:.0%} but deterministic score is 0.00"
            )

        # 2. Evidence quality guardrail — runs regardless of divergence flag
        if not _has_concrete_evidence(skill.rationale):
            skill.evidence_type = "inferred_low_confidence"
            reason = "rationale lacks concrete file/code reference"
            skill.review_reason = (
                f"{skill.review_reason}; {reason}" if skill.review_reason else reason
            )

    return assessment


# ── Main entry point ──────────────────────────────────────────────────────────

@dataclass
class LLMAssessmentDebug:
    """Observability detail for one assess_repo call — not persisted with the assessment itself."""
    prompt: str = ""
    raw_response: str = ""
    sampled_files: list[str] = field(default_factory=list)


def assess_repo(repo_path: Path) -> LLMRepoAssessment:
    """Run LLM assessment on a repo. Returns assessment; error field set if unavailable."""
    assessment, _debug = assess_repo_traced(repo_path)
    return assessment


def assess_repo_traced(repo_path: Path) -> tuple[LLMRepoAssessment, LLMAssessmentDebug]:
    """Same as assess_repo, but also returns the prompt/response/sampled-files used.

    Used by the run_pipeline orchestrator to populate RunTrace.
    """
    repo_path = repo_path.resolve()
    repo_name = repo_path.name
    debug = LLMAssessmentDebug()

    if not OPENAI_API_KEY:
        return LLMRepoAssessment(repo_name=repo_name, error="no_api_key"), debug

    ctx = _build_context(repo_path)
    debug.sampled_files = [f["path"] for f in ctx["files"]]
    prompt = _build_prompt(repo_name, ctx)
    debug.prompt = prompt

    valid_ids = set(skill_metadata().keys()) | {
        sub["id"]
        for fdom in foundation_domains()
        for sub in fdom["sub_skills"]
    }

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=2_000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
        debug.raw_response = raw
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)

        skills = []
        for s in data.get("skills", []):
            sid = s.get("skill_id", "")
            if sid not in valid_ids:
                continue
            etype = s.get("evidence_type", "inferred_exposure")
            if etype not in {"current_demonstrated", "historical_experience", "inferred_exposure"}:
                etype = "inferred_exposure"
            skills.append(LLMSkillAssessment(
                skill_id=sid,
                confidence=max(0.0, min(1.0, float(s.get("confidence", 0.5)))),
                evidence_type=etype,
                rationale=s.get("rationale", ""),
            ))

        raw_recency = data.get("repo_recency", "unknown")
        repo_recency = raw_recency if raw_recency in {"current", "historical", "unknown"} else "unknown"

        assessment = LLMRepoAssessment(
            repo_name=repo_name,
            skills=skills,
            repo_summary=data.get("repo_summary", ""),
            repo_recency=repo_recency,
            model=OPENAI_MODEL,
        )
        return assessment, debug

    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        return LLMRepoAssessment(repo_name=repo_name, error=f"parse_error: {exc}"), debug
    except openai.OpenAIError as exc:
        return LLMRepoAssessment(repo_name=repo_name, error=f"api_error: {exc}"), debug
