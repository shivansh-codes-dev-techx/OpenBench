from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import cv2
import numpy as np
from PIL import Image

from cv_engine.angles import REQUIRED_ANGLES, validate_angles
from cv_engine.inspection import inspect_all_angles
from cv_engine.quality import ImageValidationError, assess_image_quality


_COMPARISONS = (
    ("baseline_vs_initial", "baseline", "initial"),
    ("initial_vs_final", "initial", "final"),
    ("baseline_vs_final", "baseline", "final"),
)


def decode_image_bytes(image_data: bytes | bytearray | memoryview) -> np.ndarray:
    """Validate stored image bytes and decode them to an OpenCV BGR array."""
    if not isinstance(image_data, (bytes, bytearray, memoryview)):
        raise ValueError("Image data must be bytes.")

    encoded = bytes(image_data)
    if not encoded:
        raise ValueError("Image data is empty.")

    try:
        assess_image_quality(encoded)
        image = cv2.imdecode(
            np.frombuffer(encoded, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
    except (
        ImageValidationError,
        Image.DecompressionBombError,
        cv2.error,
    ) as exc:
        raise ValueError(f"Image could not be decoded: {exc}") from exc

    if (
        image is None
        or image.size == 0
        or image.dtype != np.uint8
        or image.ndim != 3
        or image.shape[2] != 3
    ):
        raise ValueError("Image could not be decoded to a valid BGR array.")

    return image


def _prepare_image_set(
    images: Mapping[str, bytes],
) -> dict[str, Any]:
    if not isinstance(images, Mapping):
        raise TypeError("Inspection images must be provided as a mapping.")

    validation = validate_angles(list(images.keys())).to_dict()
    encoded_by_angle: dict[str, bytes] = {}
    errors: dict[str, str] = {}
    duplicate_angles: set[str] = set()

    for angle, image_data in images.items():
        if not isinstance(angle, str):
            continue

        normalized_angle = angle.strip().upper()
        if normalized_angle not in REQUIRED_ANGLES:
            continue

        if normalized_angle in duplicate_angles:
            continue
        if normalized_angle in encoded_by_angle:
            del encoded_by_angle[normalized_angle]
            duplicate_angles.add(normalized_angle)
            errors[normalized_angle] = "Duplicate inspection angle."
            continue

        encoded_by_angle[normalized_angle] = image_data

    decoded_by_angle: dict[str, np.ndarray] = {}
    for angle, image_data in encoded_by_angle.items():
        try:
            decoded_by_angle[angle] = decode_image_bytes(image_data)
        except Exception as exc:
            errors[angle] = f"{type(exc).__name__}: {exc}"

    return {
        "images": decoded_by_angle,
        "errors": errors,
        "validation": validation,
        "input_errors": validation["invalid"],
    }


def _compare_pair(
    reference_name: str,
    reference: dict[str, Any],
    target_name: str,
    target: dict[str, Any],
) -> dict[str, Any]:
    result = inspect_all_angles(
        reference["images"],
        target["images"],
    ).to_dict()

    angles = result["angles"]
    for angle in REQUIRED_ANGLES:
        failures = [
            f"{stage}: {prepared['errors'][angle]}"
            for stage, prepared in (
                (reference_name, reference),
                (target_name, target),
            )
            if angle in prepared["errors"]
        ]
        if failures:
            angles[angle] = {
                "angle": angle,
                "status": "FAILED",
                "similarity_score": None,
                "difference_percentage": None,
                "potential_regions": [],
                "review_required": True,
                "attention_required": True,
                "manual_review_required": True,
                "message": "; ".join(failures),
                "quality_warnings": [],
                "alignment_warnings": [],
            }

    failed_angles = [
        angle
        for angle in REQUIRED_ANGLES
        if angles[angle]["status"] != "COMPLETED"
    ]
    missing_angles = [
        angle for angle in REQUIRED_ANGLES
        if angles[angle]["status"] == "MISSING"
    ]
    for angle in REQUIRED_ANGLES:
        angles[angle].setdefault("alignment_warnings", [])
    completed_angles = len(REQUIRED_ANGLES) - len(failed_angles)
    input_errors = {
        stage: prepared["input_errors"]
        for stage, prepared in (
            (reference_name, reference),
            (target_name, target),
        )
        if prepared["input_errors"]
    }
    attention_required = (
        result["attention_required"]
        or bool(failed_angles)
        or bool(input_errors)
    )
    overall_score_status = (
        "UNAVAILABLE"
        if result["overall_similarity_score"] is None
        else "PARTIAL"
        if completed_angles < len(REQUIRED_ANGLES) or input_errors
        else "COMPLETE"
    )

    return {
        "status": (
            "COMPLETED"
            if not failed_angles and not input_errors
            else "PARTIAL"
        ),
        "total_angles": len(REQUIRED_ANGLES),
        "completed_angles": completed_angles,
        "failed_angles": failed_angles,
        "missing_angles": missing_angles,
        "angles": angles,
        "overall_similarity_score": result["overall_similarity_score"],
        "overall_score_status": overall_score_status,
        "overall_status": overall_score_status,
        "cv_review_required": result["review_required"],
        "review_required": True,
        "attention_required": attention_required,
        "manual_review_required": True,
        "input_validation": {
            reference_name: reference["validation"],
            target_name: target["validation"],
        },
        "input_errors": input_errors,
    }


def compare_inspection_stages(
    baseline_images: Mapping[str, bytes],
    initial_images: Mapping[str, bytes],
    final_images: Mapping[str, bytes],
) -> dict[str, Any]:
    """Compare baseline/INITIAL/FINAL images for all required inspection angles."""
    prepared = {
        "baseline": _prepare_image_set(baseline_images),
        "initial": _prepare_image_set(initial_images),
        "final": _prepare_image_set(final_images),
    }

    comparisons = {
        name: _compare_pair(
            reference_name,
            prepared[reference_name],
            target_name,
            prepared[target_name],
        )
        for name, reference_name, target_name in _COMPARISONS
    }
    failed_comparisons = [
        name
        for name, result in comparisons.items()
        if result["status"] != "COMPLETED"
    ]
    completed_comparisons = len(_COMPARISONS) - len(failed_comparisons)
    overall_status = (
        "UNAVAILABLE"
        if all(
            result["overall_status"] == "UNAVAILABLE"
            for result in comparisons.values()
        )
        else "PARTIAL"
        if completed_comparisons < len(_COMPARISONS)
        else "COMPLETE"
    )

    return {
        "status": (
            "COMPLETED" if not failed_comparisons else "PARTIAL"
        ),
        "completed_comparisons": completed_comparisons,
        "failed_comparisons": failed_comparisons,
        "comparisons": comparisons,
        "overall_status": overall_status,
        "review_required": True,
        "attention_required": any(
            result["attention_required"]
            for result in comparisons.values()
        ),
        "manual_review_required": True,
    }
