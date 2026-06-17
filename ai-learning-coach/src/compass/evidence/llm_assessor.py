"""LLM-based repo skill assessment — Layer 2 evidence.

Reads README + file tree + sampled files, asks an LLM to assess which
skills are evidenced, and returns structured assessments per skill.

Output is stored separately from deterministic signals (llm_assessments
on LearnerState) and does NOT affect skill graph scores. Exposed via
`compass explain`.

See scanner.py docstring for the full three-layer architecture note.
"""
from __future__ import annotations

import json
from pathlib import Path

import anthropic

from .._data import foundation_domains, skill_metadata
from ..config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
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

Also write repo_summary: 2–3 sentences on what the repo does, its tech stack, and approximate maturity/age.

Return ONLY valid JSON, no markdown fences:
{{
  "repo_summary": "string",
  "skills": [
    {{"skill_id": "string", "confidence": 0.0, "evidence_type": "string", "rationale": "string"}}
  ]
}}"""


# ── Main entry point ──────────────────────────────────────────────────────────

def assess_repo(repo_path: Path) -> LLMRepoAssessment:
    """Run LLM assessment on a repo. Returns assessment; error field set if unavailable."""
    repo_path = repo_path.resolve()
    repo_name = repo_path.name

    if not ANTHROPIC_API_KEY:
        return LLMRepoAssessment(repo_name=repo_name, error="no_api_key")

    ctx = _build_context(repo_path)
    prompt = _build_prompt(repo_name, ctx)

    valid_ids = set(skill_metadata().keys()) | {
        sub["id"]
        for fdom in foundation_domains()
        for sub in fdom["sub_skills"]
    }

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2_000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
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

        return LLMRepoAssessment(
            repo_name=repo_name,
            skills=skills,
            repo_summary=data.get("repo_summary", ""),
            model=ANTHROPIC_MODEL,
        )

    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        return LLMRepoAssessment(repo_name=repo_name, error=f"parse_error: {exc}")
    except anthropic.APIError as exc:
        return LLMRepoAssessment(repo_name=repo_name, error=f"api_error: {exc}")
