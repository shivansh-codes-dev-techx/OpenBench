"""Adapter from OpenBench backend-shaped records to the recommender.

This module deliberately accepts objects/mappings instead of importing the
backend ORM. It can therefore be used from services, tests, or a later API
adapter without changing backend models or contracts.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from .matching import is_eligible
from .recommender import recommend_resources

BLOCKING_STATUSES = frozenset({"APPROVED", "IN_USE"})


def _get(record: Any, field: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(field, default)
    return getattr(record, field, default)


def _status_value(status: Any) -> str:
    return str(getattr(status, "value", status)).upper()


def _normalized(value: Any) -> str:
    return str(value).strip().casefold()


def booking_overlaps(
    booking: Any,
    requested_start: datetime,
    requested_end: datetime,
) -> bool:
    """Return whether a blocking booking overlaps the requested interval."""
    if _status_value(_get(booking, "status")) not in BLOCKING_STATUSES:
        return False
    start = _get(booking, "start_at")
    end = _get(booking, "end_at")
    if start is None or end is None:
        return False
    return start < requested_end and end > requested_start


def availability_from_bookings(
    bookings: Iterable[Any],
    requested_start: datetime,
    requested_end: datetime,
) -> bool:
    """Calculate availability from actual booking records.

    APPROVED and IN_USE bookings block only when their intervals overlap the
    requested interval. PENDING, RETURNED, REJECTED, and CANCELLED do not block.
    The caller must provide timezone-consistent aware datetimes.
    """
    return not any(
        booking_overlaps(booking, requested_start, requested_end)
        for booking in bookings
    )


def backend_resource_to_candidate(
    resource: Any,
    *,
    bookings: Iterable[Any],
    requested_start: datetime,
    requested_end: datetime,
    requirements: Iterable[Any] = (),
) -> dict[str, Any]:
    """Map a backend Resource and related records to recommender fields."""
    required = {
        _normalized(_get(item, "requirement_type")): _normalized(_get(item, "requirement_value"))
        for item in requirements
        if _get(item, "is_mandatory", True)
    }
    return {
        "resource_id": _get(resource, "id"),
        "category": _get(resource, "category"),
        "description": _get(resource, "description") or "",
        "location": _get(resource, "location"),
        "available": availability_from_bookings(bookings, requested_start, requested_end),
        "eligibility_required": required,
    }


def recommend_backend_resources(
    user_requirements: Mapping[str, Any],
    resources: Iterable[Any],
    *,
    qualifications: Iterable[Any],
    requirements_by_resource: Mapping[Any, Iterable[Any]],
    bookings_by_resource: Mapping[Any, Iterable[Any]],
    requested_start: datetime,
    requested_end: datetime,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Rank backend resources using authoritative VERIFIED qualifications."""
    verified = [
        {
            "type": _get(qualification, "qualification_type"),
            "title": _get(qualification, "qualification_title"),
            "status": _status_value(_get(qualification, "status")),
        }
        for qualification in qualifications
    ]
    user_eligibility = {
        _normalized(item["type"]): _normalized(item["title"])
        for item in verified
        if item["status"] == "VERIFIED"
    }
    candidates = [
        backend_resource_to_candidate(
            resource,
            bookings=bookings_by_resource.get(_get(resource, "id"), ()),
            requested_start=requested_start,
            requested_end=requested_end,
            requirements=requirements_by_resource.get(_get(resource, "id"), ()),
        )
        for resource in resources
        if _get(resource, "is_active", True)
    ]
    return recommend_resources(
        user_requirements,
        candidates,
        user_eligibility=user_eligibility,
        limit=limit,
    )
