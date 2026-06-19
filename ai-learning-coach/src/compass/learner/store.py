"""Load and save LearnerCoachState as a single atomic JSON file per learner.

Lives under data/learners/<id>/coach/state.json — a sibling of, not a
replacement for, the existing skill_graph/milestones files the old path
writes to the same learner directory.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..config import LEARNERS_DIR
from .models import LearnerCoachState


def _coach_state_path(learner_id: str) -> Path:
    return LEARNERS_DIR / learner_id / "coach" / "state.json"


def load_coach_state(learner_id: str) -> LearnerCoachState | None:
    path = _coach_state_path(learner_id)
    if not path.exists():
        return None
    return LearnerCoachState.model_validate_json(path.read_text())


def save_coach_state(state: LearnerCoachState) -> None:
    path = _coach_state_path(state.profile.learner_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)
