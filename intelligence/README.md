# OpenBench intelligence module

Optional, deterministic resource matching. It uses only the Python standard library and does not make access, safety, penalty, or booking decisions. The backend remains responsible for authoritative eligibility and live availability; owners or authorised managers retain final approval.

## API

Exact function signature:

```python
def recommend_resources(
    user_requirements: Mapping[str, Any],
    available_resources: Sequence[Mapping[str, Any]],
    *,
    user_eligibility: Mapping[str, Any] | None = None,
    limit: int | None = None,
) -> list[Recommendation]: ...
```

`user_requirements` may contain `category`, `purpose`, `location`, and `date_time` (or `time`). `available_resources` is a sequence of resource mappings. Each resource may contain `resource_id` (or `id`), `category`, `description`, `location`, and availability fields described below. `user_eligibility` maps eligibility attribute names to the user's value or values. `limit` is an optional maximum result count; omitted means no limit.

```python
from intelligence import recommend_resources

recommendations = recommend_resources(
    {"category": "electronics kit", "purpose": "robotics", "location": "North Lab", "date_time": "Mon 10"},
    resources,
    user_eligibility={"department": "ECE", "training": "certified"},
    limit=5,
)
```

Expected output is a list of mappings shaped as `{"resource_id": Any, "score": float, "reasons": list[str]}`. For example:

```python
[
    {
        "resource_id": 101,
        "score": 0.92,
        "reasons": [
            "Category relevance (100%)",
            "Purpose relevance (80%)",
            "Requested time is available (100%)",
            "Location preference (100%)",
            "Eligibility requirements satisfied (100%)",
        ],
    }
]
```

Optional `eligibility_required` maps user attribute names to required values. A list/set means any listed value is accepted. Every declared attribute must be present and match (case-insensitive); missing attributes fail closed. This hard gate runs before scoring, and ineligible resources are never included in results.

### Availability calculation

When the request has `date_time` (or `time`) and the resource supplies `available_slots`, availability is `1.0` only when the requested value exactly matches a listed slot after case-folding; otherwise it is `0.0`. A single string slot is treated as a one-item list. If either the requested time or `available_slots` is absent, availability uses the resource's `available` field: only the literal boolean `True` scores `1.0`; `False` or a missing field scores `0.0`. The backend should provide current availability data, as this helper does not query calendars or booking state.

The weights remain category 35%, purpose 25%, availability 20%, location 10%, and eligibility compatibility 10%. Text scores use query keyword overlap. Blank text preferences are neutral (100%). A passed eligibility gate gets full compatibility credit. Scores are in `[0, 1]`; ties preserve input order. Reasons show each criterion's normalized component score, including zero scores.

The function is a pure recommendation helper and has no dependency on OpenBench's authentication, booking lifecycle, database, or API. Call it after the backend has loaded candidate resources and user eligibility. Treat results as suggestions; recheck eligibility and availability in the authoritative booking flow and require owner review where applicable. If unavailable, the rest of OpenBench works without this module.

## Backend adapter

`intelligence.adapter.recommend_backend_resources` accepts backend-shaped resource, booking, requirement, and qualification records. Pass `requirements_by_resource` and `bookings_by_resource` keyed by resource ID, plus the requested timezone-aware `requested_start` and `requested_end`. It maps backend `title`-era resources without changing the backend models, excludes inactive resources, calculates availability from overlapping `APPROVED`/`IN_USE` bookings, and uses only `VERIFIED` qualifications. Keep the backend eligibility and booking approval checks authoritative.

## Tests

Run from this directory: `python -m unittest discover -s intelligence/tests -v`.
