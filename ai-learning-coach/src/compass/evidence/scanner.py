"""Evidence scanner — Evidence Validation v2.

Design principles:
  - Evidence is behavioral, not lexical. Matches are only credited when found
    in project-owned files, not vendor libraries or generated output.
  - Per-file trust classification: trusted (Python, notebooks, configs),
    semi_trusted (JS/shell, non-vendor), excluded (minified, vendor dirs).
  - Separate corpora per trust tier. Contextual (weak) patterns run only
    against trusted files; behavioral/architectural run against trusted +
    semi_trusted.
  - Minimum evidence gate: a skill is only emitted if it has at least one
    architectural or behavioral match. Contextual-only = not credited.
  - Contextual signals are suppressed when architectural is already present
    (no stacking on top of structural proof).

Future: probabilistic LLM-based skill inference
  The current scanner is fully deterministic — regex patterns against
  classified files. This is fast, auditable, and runs on every scan with
  no API cost.

  A future enhancement would add an optional LLM deep-analysis pass:
    1. One-time (or periodic) setup: user runs `compass analyze --deep REPO`.
       An LLM reads a curated subset of the repo (entry points, key modules,
       config files — not vendored code) and produces a probabilistic skill
       assessment with reasoning traces.
    2. The LLM output is stored as a separate evidence source
       (e.g. signal_type "llm_inferred") with its own weight and confidence.
    3. Subsequent `compass scan` runs stay deterministic. The LLM assessment
       acts as a one-time prior that the regex signals update on top of.
    4. The user can re-run deep analysis periodically (e.g. after a major
       feature) to refresh the prior.

  This layering keeps the fast path cheap and the slow path opt-in. The
  deterministic signals remain the ground truth for ongoing tracking;
  the LLM pass adds depth for ambiguous or novel codebases where regex
  patterns would miss intent (e.g. a custom agent loop that doesn't use
  LangGraph, or an eval harness built from scratch).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .._data import all_skill_ids, all_foundation_skill_ids, evidence_signals
from ..models import SkillEvidence

# ── Directory exclusions ──────────────────────────────────────────────────────

SKIP_DIRS = frozenset({
    # VCS / tooling
    ".git", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".eggs",
    # Build output
    "dist", "build", "node_modules",
    # Vendor / third-party JS & CSS
    "jquery", "vendor", "bower_components", "lib", "libs",
    "third_party", "external", "deps", "wwwroot",
    # Static/public web assets (usually vendored)
    "static", "public", "assets", "images", "media",
    # Project-specific generated output
    "submission", "output", "_site", "site", "docs/_build",
    "vector_store", "chroma_db", "faiss_index",
    "data", "datasets", "linkedin",
    # Test output
    "coverage", "htmlcov",
})

# ── File trust tiers ──────────────────────────────────────────────────────────

# Trusted: all three evidence levels (architectural, behavioral, contextual)
TRUSTED_SUFFIXES = frozenset({
    ".py", ".ipynb", ".ts", ".tsx",
    ".yaml", ".yml", ".toml", ".cfg", ".ini",
    ".md", ".rst", ".txt",
    ".env", ".env.example", ".dockerignore",
})
TRUSTED_NAMES = frozenset({
    "Dockerfile", "Makefile", "Pipfile", "docker-compose.yml",
    "docker-compose.yaml", ".env.example",
})

# Semi-trusted: architectural + behavioral only; no contextual credit
SEMI_TRUSTED_SUFFIXES = frozenset({
    ".js", ".jsx", ".sh", ".json",
    # General backend/frontend languages — for foundation skill detection
    ".php", ".rb", ".go", ".java", ".rs", ".cs",
    ".html", ".htm", ".css",
    # Infrastructure-as-code
    ".tf", ".hcl",
})

# Excluded suffixes — not scanned at all
EXCLUDED_SUFFIXES = frozenset({
    ".min.js", ".min.css", ".bundle.js", ".chunk.js",
    ".pb", ".onnx", ".bin", ".lock",
})

MAX_BYTES = 100_000
MAX_FILES = 500


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ClassifiedFile:
    rel_path: str
    content: str
    trust: str   # "trusted" | "semi_trusted" | "excluded"


_EVIDENCE_CONFIDENCE = {"strong": 85, "moderate": 60, "weak": 25}


@dataclass
class ScanResult:
    evidence: list[SkillEvidence]
    files_scanned: int
    repo_name: str
    errors: list[str] = field(default_factory=list)
    files_inventory: list[dict] = field(default_factory=list)  # [{"path", "trust"}] — for trace/observability only

    @property
    def by_level(self) -> dict[str, list[SkillEvidence]]:
        out: dict[str, list[SkillEvidence]] = {}
        for e in self.evidence:
            out.setdefault(e.level, []).append(e)
        return out


# ── File classification ───────────────────────────────────────────────────────

def _is_excluded_suffix(name: str) -> bool:
    """Check compound suffixes like .min.js before single suffix."""
    lower = name.lower()
    for suf in EXCLUDED_SUFFIXES:
        if lower.endswith(suf):
            return True
    return False


def _classify(rel_path: str, path: Path) -> str:
    """Return trust tier for a file: 'trusted' | 'semi_trusted' | 'excluded'."""
    name = path.name
    if _is_excluded_suffix(name):
        return "excluded"
    if name in TRUSTED_NAMES:
        return "trusted"
    suffix = path.suffix.lower()
    if suffix in TRUSTED_SUFFIXES:
        return "trusted"
    if suffix in SEMI_TRUSTED_SUFFIXES:
        return "semi_trusted"
    return "excluded"


def _read_file(path: Path) -> str:
    if path.suffix == ".ipynb":
        return _notebook_text(path)
    try:
        raw = path.read_bytes()
        return raw[:MAX_BYTES].decode("utf-8", errors="ignore")
    except OSError:
        return ""


def _notebook_text(path: Path) -> str:
    try:
        nb = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        parts: list[str] = []
        for cell in nb.get("cells", []):
            src = cell.get("source", "")
            parts.append("".join(src) if isinstance(src, list) else src)
        return "\n".join(parts)
    except (json.JSONDecodeError, OSError):
        return ""


def _collect_files(repo_path: Path) -> list[ClassifiedFile]:
    results: list[ClassifiedFile] = []
    for path in sorted(repo_path.rglob("*")):
        if len(results) >= MAX_FILES:
            break
        if not path.is_file():
            continue
        parts = path.relative_to(repo_path).parts
        # Skip hidden dirs and excluded dirs
        if any(
            p in SKIP_DIRS or (p.startswith(".") and p not in {".env", ".env.example", ".dockerignore", ".github"})
            for p in parts[:-1]
        ):
            continue
        rel = "/".join(parts)
        trust = _classify(rel, path)
        if trust == "excluded":
            continue
        results.append(ClassifiedFile(rel_path=rel, content=_read_file(path), trust=trust))
    return results


# ── Pattern compilation ───────────────────────────────────────────────────────

def _compile(pattern: str) -> re.Pattern:
    """Convert evidence_signals.yaml pattern to compiled regex.

    Patterns use | for OR. Bare * (not preceded by .) becomes .*.
    DOTALL is intentionally omitted: multi-word patterns must match within
    a single line or explicit \n. This prevents cross-line false positives
    when patterns are tested against concatenated file content.
    """
    parts = pattern.split("|")
    regexes: list[str] = []
    for part in parts:
        part = part.strip()
        converted = re.sub(r"(?<!\.)\*", ".*", part)
        regexes.append(f"(?:{converted})")
    return re.compile("|".join(regexes), re.IGNORECASE | re.MULTILINE)


def _matches_any(patterns: list, texts: list[str], errors: list[str], context: str) -> bool:
    """Return True if any pattern matches any of the texts (per-text, not concatenated).

    Each text is matched independently so patterns cannot straddle file boundaries.
    """
    for entry in patterns:
        pattern_str = entry["pattern"] if isinstance(entry, dict) else str(entry)
        try:
            regex = _compile(pattern_str)
            for text in texts:
                if regex.search(text):
                    return True
        except re.error as exc:
            errors.append(f"bad pattern {context}: {pattern_str!r} — {exc}")
    return False


# ── Scanner ───────────────────────────────────────────────────────────────────

def scan_repo(repo_path: Path) -> ScanResult:
    """Scan a local repo and return validated evidence signals.

    Enforces:
    - Vendor/library exclusion by path and suffix
    - Per-file trust tier (trusted / semi_trusted)
    - Per-file pattern matching — patterns cannot match across file boundaries
    - Minimum evidence gate: contextual-only skills are not emitted
    - Contextual signals suppressed when architectural already found
    """
    repo_path = repo_path.resolve()
    repo_name = repo_path.name
    errors: list[str] = []

    files = _collect_files(repo_path)

    # Separate file lists and path corpus by trust tier
    trusted_files = [f for f in files if f.trust == "trusted"]
    semi_files = [f for f in files if f.trust == "semi_trusted"]

    # Path corpus: one entry per file path (for path-based architectural patterns)
    path_texts = [f.rel_path for f in files]

    # Content texts per tier — matched independently (no concatenation)
    trusted_texts = [f.content for f in trusted_files]
    semi_texts = [f.content for f in semi_files]

    # What each level searches:
    # architectural: paths + trusted content + semi_trusted content
    # behavioral:    trusted content + semi_trusted content
    # contextual:    trusted content only
    arch_texts = path_texts + trusted_texts + semi_texts
    behavioral_texts = trusted_texts + semi_texts
    contextual_texts = trusted_texts

    sig_yaml = evidence_signals()
    source_weights: dict[str, float] = sig_yaml["source_weights"]
    skill_data: dict = sig_yaml.get("skills", {})

    level_texts = {
        "strong": arch_texts,
        "moderate": behavioral_texts,
        "weak": contextual_texts,
    }

    skill_levels: dict[str, set[str]] = {}

    for skill_id in all_skill_ids() + all_foundation_skill_ids():
        github_patterns = skill_data.get(skill_id, {}).get("github", {})
        matched: set[str] = set()

        for level in ("strong", "moderate", "weak"):
            level_patterns: list = github_patterns.get(level, [])
            if not level_patterns:
                continue
            texts = level_texts[level]
            if _matches_any(level_patterns, texts, errors, f"{skill_id}.{level}"):
                matched.add(level)

        if matched:
            skill_levels[skill_id] = matched

    # Apply minimum evidence gate and stacking rules, then emit evidence records
    found: list[SkillEvidence] = []

    for skill_id, matched in skill_levels.items():
        has_arch = "strong" in matched
        has_behavioral = "moderate" in matched
        has_contextual = "weak" in matched

        # Minimum evidence gate: must have architectural or behavioral to be credited
        if not has_arch and not has_behavioral:
            continue

        if has_arch:
            found.append(SkillEvidence(
                skill_id=skill_id,
                evidence_type="observed",
                recency="unknown",
                confidence=_EVIDENCE_CONFIDENCE["strong"],
                source_repo=repo_name,
            ))

        if has_behavioral:
            found.append(SkillEvidence(
                skill_id=skill_id,
                evidence_type="observed",
                recency="unknown",
                confidence=_EVIDENCE_CONFIDENCE["moderate"],
                source_repo=repo_name,
            ))

        # Contextual only adds when behavioral present and architectural absent
        if has_contextual and has_behavioral and not has_arch:
            found.append(SkillEvidence(
                skill_id=skill_id,
                evidence_type="inferred",
                recency="unknown",
                confidence=_EVIDENCE_CONFIDENCE["weak"],
                source_repo=repo_name,
            ))

    return ScanResult(
        evidence=found,
        files_scanned=len(files),
        repo_name=repo_name,
        errors=errors,
        files_inventory=[{"path": f.rel_path, "trust": f.trust} for f in files],
    )
