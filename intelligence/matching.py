"""Text normalization and conservative eligibility checks."""

import re
from collections.abc import Mapping
from typing import Any


def tokens(value: Any) -> set[str]:
    """Return lowercase alphanumeric keywords from a string or collection."""
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set, frozenset)):
        value = " ".join(str(item) for item in value)
    return set(re.findall(r"[a-z0-9]+", str(value).casefold()))


def text_similarity(query: Any, candidate: Any) -> float:
    """Token overlap normalized by query size; empty queries are neutral."""
    wanted = tokens(query)
    if not wanted:
        return 1.0
    found = tokens(candidate)
    return len(wanted & found) / len(wanted)


def is_eligible(user_eligibility: Any, required_eligibility: Any) -> bool:
    """Check resource requirements as a hard gate.

    Each key in ``required_eligibility`` must be present for the user. Scalar
    requirements must match case-insensitively; a collection means any listed
    value is accepted. Empty requirements permit everyone. Missing or malformed
    user attributes fail closed when a resource declares that attribute.
    """
    if not required_eligibility:
        return True
    if not isinstance(required_eligibility, Mapping) or not isinstance(user_eligibility, Mapping):
        return False
    for key, required in required_eligibility.items():
        if key not in user_eligibility:
            return False
        actual = user_eligibility[key]
        accepted = required if isinstance(required, (list, tuple, set, frozenset)) else [required]
        actual_values = actual if isinstance(actual, (list, tuple, set, frozenset)) else [actual]
        if not any(str(a).casefold() == str(r).casefold() for a in actual_values for r in accepted):
            return False
    return True
