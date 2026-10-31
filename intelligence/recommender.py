"""Public resource recommendation entry point."""

from collections.abc import Mapping, Sequence
from typing import Any

from .matching import is_eligible
from .schemas import Recommendation
from .scoring import component_scores, explain_scores, weighted_score


def recommend_resources(
    user_requirements: Mapping[str, Any],
    available_resources: Sequence[Mapping[str, Any]],
    *,
    user_eligibility: Mapping[str, Any] | None = None,
    limit: int | None = None,
) -> list[Recommendation]:
    """Rank eligible resources using deterministic weighted keyword matching.

    Resource mappings use ``resource_id``, ``category``, ``description``,
    ``location``, and either ``available`` or ``available_slots``. Optional
    ``eligibility_required`` is a mapping of required user attributes. The
    requirement and resource ``date_time``/``time`` values are compared exactly
    against ``available_slots`` when slots are supplied. Eligibility is always
    checked before scoring and ineligible resources are never returned.
    """
    ranked: list[tuple[int, Recommendation]] = []
    for index, resource in enumerate(available_resources):
        if not is_eligible(user_eligibility, resource.get("eligibility_required", {})):
            continue
        scores = component_scores(user_requirements, resource)
        ranked.append((index, {
            "resource_id": resource.get("resource_id", resource.get("id")),
            "score": weighted_score(scores),
            "reasons": explain_scores(scores),
        }))
    ranked.sort(key=lambda item: (-item[1]["score"], item[0]))
    results = [item[1] for item in ranked]
    return results if limit is None else results[:max(0, limit)]
