"""Adapter from OpenBench backend-shaped records to the recommender.

This module deliberately accepts objects/mappings instead of importing the
backend ORM. It can therefore be used from services, tests, or a later API
adapter without changing backend models or contracts.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
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


def _as_utc(value: Any) -> datetime | None:
    """Normalize an aware datetime; reject missing, naive, or invalid values."""
    if not isinstance(value, datetime) or value.utcoffset() is None:
        return None
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        return None


def _requested_interval(requested_start: datetime, requested_end: datetime) -> tuple[datetime, datetime]:
    start = _as_utc(requested_start)
    end = _as_utc(requested_end)
    if start is None or end is None or start >= end:
        raise ValueError("requested interval must use aware datetimes with start before end")
    return start, end


def booking_overlaps(
    booking: Any,
    requested_start: datetime,
    requested_end: datetime,
) -> bool:
    """Return whether a blocking booking overlaps the requested half-open interval.

    Malformed blocking records fail closed as overlapping, preventing bad
    booking data from making the resource appear available.
    """
    if _status_value(_get(booking, "status")) not in BLOCKING_STATUSES:
        return False
    requested_start_utc, requested_end_utc = _requested_interval(requested_start, requested_end)
    start = _get(booking, "start_at")
    end = _get(booking, "end_at")
    start_utc = _as_utc(start)
    end_utc = _as_utc(end)
    if start_utc is None or end_utc is None or start_utc >= end_utc:
        return True
    return start_utc < requested_end_utc and end_utc > requested_start_utc


def availability_from_bookings(
    bookings: Iterable[Any],
    requested_start: datetime,
    requested_end: datetime,
) -> bool:
    """Calculate availability from actual booking records.

    APPROVED and IN_USE bookings block only when their intervals overlap the
    requested interval. PENDING, RETURNED, REJECTED, and CANCELLED do not block.
    Intervals are half-open: touching endpoints do not overlap. All timestamps
    must be timezone-aware; requested intervals are rejected when malformed,
    while malformed blocking bookings fail closed as overlapping.
    """
    _requested_interval(requested_start, requested_end)
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
    required = [
        (_normalized(_get(item, "requirement_type")), _normalized(_get(item, "requirement_value")))
        for item in requirements
        if _get(item, "is_mandatory", True)
    ]
    return {
        "resource_id": _get(resource, "id"),
        "title": _get(resource, "title") or "",
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
    requesting_student_id: Any,
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
        if _get(qualification, "user_id") == requesting_student_id
    ]
    user_eligibility: dict[str, set[str]] = {}
    for item in verified:
        if item["status"] == "VERIFIED":
            user_eligibility.setdefault(_normalized(item["type"]), set()).add(
                _normalized(item["title"])
            )
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
