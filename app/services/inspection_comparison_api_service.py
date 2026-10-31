from __future__ import annotations

import logging
from collections.abc import Mapping
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
from cv_engine.angles import REQUIRED_ANGLES


logger = logging.getLogger(__name__)

_COMPARISON_STAGES = {
    "baseline_vs_initial": ("baseline", "initial"),
    "initial_vs_final": ("initial", "final"),
    "baseline_vs_final": ("baseline", "final"),
}


class InspectionComparisonError(RuntimeError):
    """Raised when the CV engine cannot produce an inspection comparison."""


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

    stages: dict[str, dict[str, Any]] = {
        "baseline": {
            "status": "UNAVAILABLE",
            "report_id": None,
            "present_angles": [],
            "missing_angles": list(REQUIRED_ANGLES),
            "invalid_angles": [],
            "reason": "No immutable baseline snapshot is available for this booking.",
        }
    }
    image_sets: dict[str, dict[str, bytes]] = {"baseline": {}}

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

    comparisons: dict[str, dict[str, Any]] = {}
    baseline_reason = stages["baseline"]["reason"]
    for name in ("baseline_vs_initial", "baseline_vs_final"):
        comparisons[name] = _unavailable_comparison(
            name,
            stages,
            baseline_reason,
        )

    initial_ready = stages["initial"]["status"] == "AVAILABLE"
    final_ready = stages["final"]["status"] == "AVAILABLE"
    if not initial_ready or not final_ready:
        missing_stage_reasons = [
            stages[stage]["reason"]
            for stage, is_ready in (
                ("initial", initial_ready),
                ("final", final_ready),
            )
            if not is_ready
        ]
        comparisons["initial_vs_final"] = _unavailable_comparison(
            "initial_vs_final",
            stages,
            " ".join(missing_stage_reasons),
        )
    else:
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

        initial_final = engine_results["comparisons"]["initial_vs_final"]
        initial_final["missing_angles"] = {
            "initial": stages["initial"]["missing_angles"],
            "final": stages["final"]["missing_angles"],
        }
        comparisons["initial_vs_final"] = initial_final

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
