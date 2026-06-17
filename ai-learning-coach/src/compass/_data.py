"""Cached loaders for competency model YAML files."""
from __future__ import annotations

from functools import lru_cache

import yaml

from .config import COMPETENCY_DIR


@lru_cache(maxsize=None)
def skills() -> dict:
    return yaml.safe_load((COMPETENCY_DIR / "skills.yaml").read_text())


@lru_cache(maxsize=None)
def evidence_signals() -> dict:
    # evidence_signals.yaml uses --- to separate two YAML documents; merge them.
    text = (COMPETENCY_DIR / "evidence_signals.yaml").read_text()
    merged: dict = {}
    for doc in yaml.safe_load_all(text):
        if doc:
            merged.update(doc)
    return merged


@lru_cache(maxsize=None)
def role_requirements() -> dict:
    return yaml.safe_load((COMPETENCY_DIR / "role_requirements.yaml").read_text())


def all_skill_ids() -> list[str]:
    return [sub["id"] for domain in skills()["domains"] for sub in domain["sub_skills"]]


def all_foundation_skill_ids() -> list[str]:
    return [
        sub["id"]
        for domain in skills().get("foundation_domains", [])
        for sub in domain["sub_skills"]
    ]


def skill_domain_map() -> dict[str, str]:
    """Returns {skill_id: domain_id} for AI skills only."""
    result = {}
    for domain in skills()["domains"]:
        for sub in domain["sub_skills"]:
            result[sub["id"]] = domain["id"]
    return result


def domains() -> list[dict]:
    """Returns [{id, name}] for all 8 AI domains."""
    return [{"id": d["id"], "name": d["name"]} for d in skills()["domains"]]


def foundation_domains() -> list[dict]:
    """Returns [{id, name, sub_skills}] for foundation domains."""
    return skills().get("foundation_domains", [])


def foundation_credit_map() -> dict[str, dict[str, float]]:
    """Returns {foundation_skill_id: {ai_skill_id: max_boost}} from skills.yaml."""
    result: dict[str, dict[str, float]] = {}
    for domain in skills().get("foundation_domains", []):
        for sub in domain["sub_skills"]:
            credits = sub.get("ai_credits", {})
            if credits:
                result[sub["id"]] = credits
    return result


def sub_skills_by_domain(domain_id: str) -> list[dict]:
    for d in skills()["domains"]:
        if d["id"] == domain_id:
            return d["sub_skills"]
    return []


def pre_seeded_scores(background: str) -> dict[str, float]:
    return role_requirements()["roles"][background].get("pre_seeded_scores", {})


def depth_threshold(desired_depth: str) -> float:
    tiers = role_requirements().get("depth_tiers", {})
    return tiers.get(desired_depth, {}).get("completion_threshold", 0.60)


def role_priority_weights(background: str) -> dict[str, float]:
    return role_requirements()["roles"][background].get("priority_weights", {})


def skill_metadata() -> dict[str, dict]:
    """Return {skill_id: {domain, name, prerequisites, min_prerequisite_score, activation_gate}}."""
    result = {}
    for domain in skills()["domains"]:
        for sub in domain["sub_skills"]:
            result[sub["id"]] = {
                "domain": domain["id"],
                "name": sub["name"],
                "prerequisites": sub.get("prerequisites", []),
                "min_prerequisite_score": sub.get("min_prerequisite_score", 0.30),
                "activation_gate": sub.get("activation_gate"),
            }
    return result
