"""Input/output conventions for the dependency-free recommender.

The public API accepts mappings so a backend can adapt its own models without
coupling this module to a database or web framework.
"""

from typing import Any, Mapping, TypedDict


class Recommendation(TypedDict):
    resource_id: Any
    score: float
    reasons: list[str]


Requirements = Mapping[str, Any]
Resource = Mapping[str, Any]
