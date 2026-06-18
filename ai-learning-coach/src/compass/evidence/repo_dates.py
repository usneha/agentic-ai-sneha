"""Deterministic repo chronology — git commit-date extraction.

Pure shell-out to `git log`, no LLM, no network. Used by `compass story` to
ground builder-journey narratives in real repository history rather than
inferred or fictional timelines.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RepoChronology:
    repo_name: str
    first_commit_date: str | None  # YYYY-MM-DD, None if not a git repo or no commits
    last_commit_date: str | None
    is_git_repo: bool


def get_repo_chronology(repo_path: Path) -> RepoChronology:
    """Extract first/last commit dates via `git log`.

    Handles two cases: repo_path is itself a git repo root, OR repo_path is a
    subdirectory of a larger repo (a common monorepo layout) — in the latter
    case, history is scoped to commits that touched that subdirectory via
    `git log -- <path>`, rather than the whole enclosing repo's history.

    Returns all-None fields gracefully if repo_path isn't inside a git repo,
    has no commits, or git is unavailable — never fabricates a date.
    """
    repo_path = repo_path.resolve()
    repo_name = repo_path.name

    try:
        toplevel = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if toplevel.returncode != 0 or not toplevel.stdout.strip():
            return RepoChronology(repo_name, None, None, is_git_repo=False)

        root = Path(toplevel.stdout.strip())
        pathspec = None if repo_path == root else str(repo_path.relative_to(root))

        log_args = ["git", "-C", str(root), "log", "--format=%ad", "--date=short"]
        if pathspec:
            log_args += ["--", pathspec]

        # Newest-first by default — dates[0] is the last commit, dates[-1] the first.
        dates = subprocess.run(
            log_args, capture_output=True, text=True, timeout=10, check=False,
        ).stdout.strip().splitlines()

        if not dates:
            return RepoChronology(repo_name, None, None, is_git_repo=True)
        return RepoChronology(repo_name, dates[-1], dates[0], is_git_repo=True)
    except (subprocess.SubprocessError, OSError, ValueError):
        return RepoChronology(repo_name, None, None, is_git_repo=True)
