"""Load and save learner state as atomic JSON files."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from ..config import LEARNERS_DIR
from ..models import (
    CurriculumModule,
    GitHubCache,
    JournalEntry,
    LearnerProfile,
    LearnerState,
    LLMRepoAssessment,
    Milestone,
    Override,
    SkillEvidence,
    SkillScore,
)


def learner_dir(learner_id: str) -> Path:
    return LEARNERS_DIR / learner_id


def _atomic_write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def load_state(learner_id: str) -> LearnerState | None:
    d = learner_dir(learner_id)
    profile_file = d / "profile.json"
    if not profile_file.exists():
        return None

    profile = LearnerProfile.model_validate_json(profile_file.read_text())

    skill_graph: dict[str, SkillScore] = {}
    sg_file = d / "skill_graph.json"
    if sg_file.exists():
        raw = json.loads(sg_file.read_text())
        skill_graph = {k: SkillScore.model_validate(v) for k, v in raw.items()}

    active_milestone = None
    completed_milestones: list[Milestone] = []
    ms_file = d / "milestones.json"
    if ms_file.exists():
        raw = json.loads(ms_file.read_text())
        active_milestone = Milestone.model_validate(raw["active"]) if raw.get("active") else None
        completed_milestones = [Milestone.model_validate(m) for m in raw.get("completed", [])]

    journal_entries: list[JournalEntry] = []
    j_file = d / "journal.json"
    if j_file.exists():
        journal_entries = [JournalEntry.model_validate(e) for e in json.loads(j_file.read_text())]

    github_cache = None
    gc_file = d / "github_cache.json"
    if gc_file.exists():
        github_cache = GitHubCache.model_validate_json(gc_file.read_text())

    overrides: list[Override] = []
    ov_file = d / "overrides.json"
    if ov_file.exists():
        overrides = [Override.model_validate(o) for o in json.loads(ov_file.read_text())]

    modules: dict[str, CurriculumModule] = {}
    modules_dir = d / "modules"
    if modules_dir.exists():
        for f in modules_dir.glob("*.json"):
            m = CurriculumModule.model_validate_json(f.read_text())
            modules[m.milestone_id] = m

    llm_assessments: list[LLMRepoAssessment] = []
    llm_file = d / "llm_assessments.json"
    if llm_file.exists():
        llm_assessments = [LLMRepoAssessment.model_validate(a) for a in json.loads(llm_file.read_text())]

    evidence: list[SkillEvidence] = []
    ev_file = d / "evidence.json"
    if ev_file.exists():
        evidence = [SkillEvidence.model_validate(e) for e in json.loads(ev_file.read_text())]

    return LearnerState(
        profile=profile,
        evidence=evidence,
        skill_graph=skill_graph,
        active_milestone=active_milestone,
        completed_milestones=completed_milestones,
        journal_entries=journal_entries,
        github_cache=github_cache,
        overrides=overrides,
        modules=modules,
        llm_assessments=llm_assessments,
    )


def save_state(state: LearnerState) -> None:
    d = learner_dir(state.profile.learner_id)
    d.mkdir(parents=True, exist_ok=True)

    _atomic_write(
        d / "profile.json",
        state.profile.model_dump(mode="json"),
    )
    _atomic_write(
        d / "skill_graph.json",
        {k: v.model_dump(mode="json") for k, v in state.skill_graph.items()},
    )
    _atomic_write(
        d / "milestones.json",
        {
            "active": state.active_milestone.model_dump(mode="json") if state.active_milestone else None,
            "completed": [m.model_dump(mode="json") for m in state.completed_milestones],
        },
    )
    _atomic_write(
        d / "journal.json",
        [e.model_dump(mode="json") for e in state.journal_entries],
    )
    gc_file = d / "github_cache.json"
    if state.github_cache:
        _atomic_write(gc_file, state.github_cache.model_dump(mode="json"))
    elif gc_file.exists():
        gc_file.unlink()
    _atomic_write(
        d / "overrides.json",
        [o.model_dump(mode="json") for o in state.overrides],
    )

    if state.modules:
        modules_dir = d / "modules"
        modules_dir.mkdir(exist_ok=True)
        for milestone_id, module in state.modules.items():
            _atomic_write(
                modules_dir / f"{milestone_id}.json",
                module.model_dump(mode="json"),
            )

    llm_file = d / "llm_assessments.json"
    if state.llm_assessments:
        _atomic_write(llm_file, [a.model_dump(mode="json") for a in state.llm_assessments])
    elif llm_file.exists():
        llm_file.unlink()

    ev_file = d / "evidence.json"
    if state.evidence:
        _atomic_write(ev_file, [e.model_dump(mode="json") for e in state.evidence])
    elif ev_file.exists():
        ev_file.unlink()


def backup_state(learner_id: str) -> None:
    d = learner_dir(learner_id)
    backup = d.parent / f"{learner_id}.backup"
    if d.exists():
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(d, backup)


def list_learners() -> list[str]:
    if not LEARNERS_DIR.exists():
        return []
    return sorted(
        d.name for d in LEARNERS_DIR.iterdir()
        if d.is_dir() and not d.name.endswith(".backup")
    )
