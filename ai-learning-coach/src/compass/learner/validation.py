"""Claim validation for the learner-centered coaching path.

Hard rule: the LLM can reason over evidence, but cannot invent it. Every
claim that cites evidence does so by EvidenceItem id; ids that don't exist
in the evidence bundle passed to the prompt are stripped. A claim that cites
zero evidence (every id it gave was invalid, or it gave none) is dropped
entirely rather than kept with an empty evidence list — an unsupported
claim is not a downgraded claim, it's not a claim.

Confidence is the LLM's subjective coaching judgment, not a measured score —
validation only clamps it to the valid [0, 1] range, never rejects on value.
"""
from __future__ import annotations

from .models import (
    CapabilityClaim,
    CoachBelief,
    GapClaim,
    GrowthEdge,
    Strength,
    UncertaintyClaim,
)


def _clamp_confidence(raw: object) -> float:
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return 0.5


def _valid_evidence_ids(raw_ids: object, valid_ids: set[str]) -> list[str]:
    if not isinstance(raw_ids, list):
        return []
    return [i for i in raw_ids if isinstance(i, str) and i in valid_ids]


def _strings(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [s.strip() for s in raw if isinstance(s, str) and s.strip()]


def validate_capability(raw: dict, valid_ids: set[str]) -> CapabilityClaim | None:
    capability = str(raw.get("capability", "")).strip()
    ids = _valid_evidence_ids(raw.get("evidence_ids"), valid_ids)
    if not capability or not ids:
        return None
    return CapabilityClaim(
        capability=capability,
        confidence=_clamp_confidence(raw.get("confidence")),
        evidence_ids=ids,
        why_it_matters=str(raw.get("why_it_matters", "")).strip(),
    )


def validate_gap(raw: dict, valid_ids: set[str]) -> GapClaim | None:
    gap = str(raw.get("gap", "")).strip()
    ids = _valid_evidence_ids(raw.get("evidence_ids"), valid_ids)
    if not gap or not ids:
        return None
    return GapClaim(
        gap=gap,
        confidence=_clamp_confidence(raw.get("confidence")),
        evidence_ids=ids,
        why_it_matters=str(raw.get("why_it_matters", "")).strip(),
    )


def validate_uncertainty(raw: dict) -> UncertaintyClaim | None:
    uncertainty = str(raw.get("uncertainty", "")).strip()
    if not uncertainty:
        return None
    return UncertaintyClaim(
        uncertainty=uncertainty,
        missing_evidence=_strings(raw.get("missing_evidence")),
        how_to_test=str(raw.get("how_to_test", "")).strip(),
    )


def validate_strength(raw: dict, valid_ids: set[str]) -> Strength | None:
    strength = str(raw.get("strength", "")).strip()
    ids = _valid_evidence_ids(raw.get("evidence_ids"), valid_ids)
    if not strength or not ids:
        return None
    return Strength(strength=strength, confidence=_clamp_confidence(raw.get("confidence")), evidence_ids=ids)


def validate_growth_edge(raw: dict, valid_ids: set[str]) -> GrowthEdge | None:
    growth_edge = str(raw.get("growth_edge", "")).strip()
    ids = _valid_evidence_ids(raw.get("evidence_ids"), valid_ids)
    if not growth_edge or not ids:
        return None
    return GrowthEdge(growth_edge=growth_edge, confidence=_clamp_confidence(raw.get("confidence")), evidence_ids=ids)


def validate_belief(raw: dict, valid_ids: set[str]) -> CoachBelief | None:
    belief = str(raw.get("belief", "")).strip()
    ids = _valid_evidence_ids(raw.get("supporting_evidence_ids"), valid_ids)
    if not belief or not ids:
        return None
    return CoachBelief(
        belief=belief,
        confidence=_clamp_confidence(raw.get("confidence")),
        supporting_evidence_ids=ids,
        missing_evidence=_strings(raw.get("missing_evidence")),
        could_be_disproven_by=(str(raw["could_be_disproven_by"]).strip() or None) if raw.get("could_be_disproven_by") else None,
    )
