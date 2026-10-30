"""Explainable weighted matching scores, kept separate from eligibility."""

from collections.abc import Mapping
from typing import Any

from .matching import text_similarity

WEIGHTS = {
    "category": 0.35,
    "purpose": 0.25,
    "availability": 0.20,
    "location": 0.10,
    "eligibility": 0.10,
}


def _availability_score(requirements: Mapping[str, Any], resource: Mapping[str, Any]) -> float:
    desired = requirements.get("date_time", requirements.get("time"))
    slots = resource.get("available_slots")
    if desired is not None and slots is not None:
        if isinstance(slots, str):
            slots = [slots]
        return 1.0 if str(desired).casefold() in {str(slot).casefold() for slot in slots} else 0.0
    available = resource.get("available", True)
    return 1.0 if available is True else 0.0


def component_scores(requirements: Mapping[str, Any], resource: Mapping[str, Any]) -> dict[str, float]:
    """Return normalized 0..1 scores for each weighted criterion."""
    return {
        "category": text_similarity(requirements.get("category"), resource.get("category")),
        "purpose": text_similarity(requirements.get("purpose"), resource.get("description", "")),
        "availability": _availability_score(requirements, resource),
        "location": text_similarity(requirements.get("location"), resource.get("location")),
        # A successful hard-gate check earns full compatibility credit.
        "eligibility": 1.0,
    }


def weighted_score(scores: Mapping[str, float]) -> float:
    return round(sum(WEIGHTS[key] * scores[key] for key in WEIGHTS), 4)


def explain_scores(scores: Mapping[str, float]) -> list[str]:
    labels = {
        "category": "Category relevance",
        "purpose": "Purpose relevance",
        "availability": "Requested time is available",
        "location": "Location preference",
        "eligibility": "Eligibility requirements satisfied",
    }
    return [f"{labels[key]} ({scores[key]:.0%})" for key in WEIGHTS]
