from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.condition_report import ConditionReport
from app.models.condition_report_image import ConditionReportImage
from app.models.user import User
from app.services.booking_service import get_booking_by_id
from app.services.inspection_comparison_service import (
    compare_inspection_stages,
)
from cv_engine.angles import REQUIRED_ANGLES, validate_angles


logger = logging.getLogger(__name__)

BaselineImageProvider = Callable[
    [Session, int, User], Mapping[str, bytes] | None
]

_COMPARISON_STAGES = {
    "baseline_vs_initial": ("baseline", "initial"),
    "initial_vs_final": ("initial", "final"),
    "baseline_vs_final": ("baseline", "final"),
}


class InspectionComparisonError(RuntimeError):
    """Raised when the CV engine cannot produce an inspection comparison."""


def _snapshot_baseline_provider(
    db: Session,
    booking_id: int,
    actor: User,
) -> Mapping[str, bytes] | None:
    try:
        from app.services.booking_baseline_snapshot_service import (
            get_booking_baseline_snapshot_images,
        )
        from app.services.baseline_snapshot_adapter import (
            snapshot_records_to_angle_bytes,
        )
    except ModuleNotFoundError as exc:
        if exc.name in {
            "app.services.booking_baseline_snapshot_service",
            "app.services.baseline_snapshot_adapter",
        }:
            logger.info("Baseline snapshot service is not available yet")
            return None
        raise

    snapshot, image_rows = get_booking_baseline_snapshot_images(
        db,
        booking_id=booking_id,
        actor=actor,
    )
    if snapshot is None:
        return None
    return snapshot_records_to_angle_bytes(image_rows)


def _baseline_stage_summary(
    images: Mapping[str, bytes],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    validation = validate_angles(list(images.keys()))
    present_angles = set(validation.present)
    invalid_angles = sorted({
        *validation.invalid,
        *validation.duplicates,
    })
    return (
        {
            "status": "AVAILABLE",
            "report_id": None,
            "present_angles": [
                angle for angle in REQUIRED_ANGLES if angle in present_angles
            ],
            "missing_angles": [
                angle for angle in REQUIRED_ANGLES if angle not in present_angles
            ],
            "invalid_angles": invalid_angles,
            "reason": None,
        },
        dict(images),
    )


def _stage_summary(
    report: ConditionReport | None,
    image_rows: list[ConditionReportImage] | None = None,
    *,
    unavailable_reason: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    if report is None:
        return (
            {
                "status": "UNAVAILABLE",
                "report_id": None,
                "present_angles": [],
                "missing_angles": list(REQUIRED_ANGLES),
                "invalid_angles": [],
                "reason": unavailable_reason,
            },
            {},
        )

    image_rows = image_rows or []
    image_bytes = {image.angle: bytes(image.image_data) for image in image_rows}
    present_angles = {
        image.angle.strip().upper()
        for image in image_rows
        if image.angle.strip().upper() in REQUIRED_ANGLES
    }
    invalid_angles = sorted({
        image.angle
        for image in image_rows
        if image.angle.strip().upper() not in REQUIRED_ANGLES
    })

    return (
        {
            "status": "AVAILABLE",
            "report_id": report.id,
            "present_angles": [
                angle for angle in REQUIRED_ANGLES if angle in present_angles
            ],
            "missing_angles": [
                angle for angle in REQUIRED_ANGLES if angle not in present_angles
            ],
            "invalid_angles": invalid_angles,
            "reason": None,
        },
        image_bytes,
    )


def _unavailable_comparison(
    name: str,
    stages: Mapping[str, dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    reference_name, target_name = _COMPARISON_STAGES[name]
    return {
        "status": "UNAVAILABLE",
        "reason": reason,
        "total_angles": len(REQUIRED_ANGLES),
        "completed_angles": 0,
        "failed_angles": [],
        "missing_angles": {
            reference_name: stages[reference_name]["missing_angles"],
            target_name: stages[target_name]["missing_angles"],
        },
        "angles": {
            angle: {
                "angle": angle,
                "status": "UNAVAILABLE",
                "similarity_score": None,
                "difference_percentage": None,
                "potential_regions": [],
                "review_required": True,
                "attention_required": True,
                "manual_review_required": True,
                "message": reason,
                "quality_warnings": [],
                "alignment_warnings": [],
            }
            for angle in REQUIRED_ANGLES
        },
        "overall_similarity_score": None,
        "overall_score_status": "UNAVAILABLE",
        "overall_status": "UNAVAILABLE",
        "review_required": True,
        "attention_required": True,
        "manual_review_required": True,
    }


def get_booking_inspection_comparisons(
    db: Session,
    booking_id: int,
    actor: User,
    *,
    baseline_provider: BaselineImageProvider | None = None,
) -> dict[str, Any]:
    """Return authorized, metadata-only comparison results for one booking."""
    booking: Booking = get_booking_by_id(db, booking_id, actor)

    reports = list(db.scalars(
        select(ConditionReport)
        .where(
            ConditionReport.booking_id == booking_id,
            ConditionReport.report_type.in_(("INITIAL", "FINAL")),
        )
        .order_by(ConditionReport.id)
    ).all())
    reports_by_stage = {
        stage: [
            report for report in reports if report.report_type == stage.upper()
        ]
        for stage in ("initial", "final")
    }

    baseline_reason = "No immutable baseline snapshot is available for this booking."
    baseline_summary: dict[str, Any]
    baseline_images: dict[str, bytes] = {}
    try:
        provider = baseline_provider or _snapshot_baseline_provider
        provided_images = provider(db, booking_id, actor)
        if provided_images is None or (
            isinstance(provided_images, Mapping) and not provided_images
        ):
            baseline_summary, _ = _stage_summary(
                None,
                unavailable_reason=baseline_reason,
            )
        elif not isinstance(provided_images, Mapping):
            baseline_summary, _ = _stage_summary(
                None,
                unavailable_reason=(
                    "Baseline provider returned an invalid image mapping."
                ),
            )
        else:
            baseline_summary, baseline_images = _baseline_stage_summary(
                provided_images
            )
    except LookupError:
        baseline_summary, _ = _stage_summary(
            None,
            unavailable_reason=baseline_reason,
        )
    except Exception:
        logger.exception(
            "Baseline image provider failed for booking %s",
            booking_id,
        )
        baseline_summary, _ = _stage_summary(
            None,
            unavailable_reason="Baseline image retrieval failed.",
        )

    stages: dict[str, dict[str, Any]] = {"baseline": baseline_summary}
    image_sets: dict[str, dict[str, bytes]] = {"baseline": baseline_images}

    for stage, stage_reports in reports_by_stage.items():
        if not stage_reports:
            summary, stage_images = _stage_summary(
                None,
                unavailable_reason=f"No {stage.upper()} condition report is available.",
            )
        elif len(stage_reports) > 1:
            summary, stage_images = _stage_summary(
                None,
                unavailable_reason=(
                    f"Multiple {stage.upper()} condition reports exist; "
                    "the comparison source is ambiguous."
                ),
            )
        else:
            report = stage_reports[0]
            images = list(db.scalars(
                select(ConditionReportImage)
                .where(ConditionReportImage.report_id == report.id)
                .order_by(ConditionReportImage.id)
            ).all())
            summary, stage_images = _stage_summary(report, images)

        stages[stage] = summary
        image_sets[stage] = stage_images

    ready_pairs = {
        name: all(
            stages[stage]["status"] == "AVAILABLE"
            for stage in pair
        )
        for name, pair in _COMPARISON_STAGES.items()
    }
    comparisons: dict[str, dict[str, Any]] = {}
    engine_results = None
    if any(ready_pairs.values()):
        try:
            engine_results = compare_inspection_stages(
                image_sets["baseline"],
                image_sets["initial"],
                image_sets["final"],
            )
        except Exception as exc:
            logger.exception(
                "CV comparison failed for booking %s",
                booking_id,
            )
            raise InspectionComparisonError(
                "Inspection comparison could not be completed."
            ) from exc

    for name, (reference_name, target_name) in _COMPARISON_STAGES.items():
        if ready_pairs[name] and engine_results is not None:
            comparison = engine_results["comparisons"][name]
            comparison["missing_angles"] = {
                reference_name: stages[reference_name]["missing_angles"],
                target_name: stages[target_name]["missing_angles"],
            }
            comparisons[name] = comparison
            continue

        unavailable_stages = [
            stages[stage]["reason"]
            for stage in (reference_name, target_name)
            if stages[stage]["status"] != "AVAILABLE"
            and stages[stage]["reason"]
        ]
        reason = " ".join(unavailable_stages) or (
            "Required comparison images are unavailable."
        )
        comparisons[name] = _unavailable_comparison(name, stages, reason)

    unavailable = [
        name
        for name, result in comparisons.items()
        if result["status"] == "UNAVAILABLE"
    ]
    failed = [
        name
        for name, result in comparisons.items()
        if result["status"] not in ("COMPLETED", "UNAVAILABLE")
    ]
    status_value = (
        "NOT_READY"
        if unavailable
        else "PARTIAL" if failed
        else "COMPLETED"
    )

    return {
        "booking_id": booking.id,
        "status": status_value,
        "stages": stages,
        "comparisons": comparisons,
        "unavailable_comparisons": unavailable,
        "failed_comparisons": failed,
        "review_required": True,
        "attention_required": any(
            result["attention_required"]
            for result in comparisons.values()
        ),
        "manual_review_required": True,
    }
