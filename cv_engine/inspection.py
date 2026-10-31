
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from cv_engine.alignment import align_images
from cv_engine.angles import REQUIRED_ANGLES, validate_angles
from cv_engine.comparison import compare_images
from cv_engine.preprocessing import preprocess_image
from cv_engine.quality import assess_image_quality


@dataclass
class AngleInspectionResult:
    angle: str
    status: str
    similarity_score: float | None
    difference_percentage: float | None
    potential_regions: list[dict]
    review_required: bool
    message: str
    quality_warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "angle": self.angle,
            "status": self.status,
            "similarity_score": self.similarity_score,
            "difference_percentage": self.difference_percentage,
            "potential_regions": self.potential_regions,
            "review_required": self.review_required,
            "message": self.message,
            "quality_warnings": self.quality_warnings,
        }


@dataclass
class InspectionResult:
    status: str
    total_angles: int
    completed_angles: int
    failed_angles: list[str]
    angles: dict[str, AngleInspectionResult]
    overall_similarity_score: float | None
    review_required: bool

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "total_angles": self.total_angles,
            "completed_angles": self.completed_angles,
            "failed_angles": self.failed_angles,
            "angles": {
                name: result.to_dict()
                for name, result in self.angles.items()
            },
            "overall_similarity_score": self.overall_similarity_score,
            "review_required": self.review_required,
        }


def _assess_array_quality(image: np.ndarray):
    """
    Convert an OpenCV image array to PNG bytes
    and assess its image quality.
    """

    if not isinstance(image, np.ndarray):
        raise ValueError("Image must be a NumPy array.")

    if image.size == 0:
        raise ValueError("Inspection image is empty.")

    if image.dtype != np.uint8:
        raise ValueError("Inspection image must have uint8 data type.")

    if image.ndim == 2:
        pass

    elif image.ndim == 3 and image.shape[2] in (3, 4):
        pass

    else:
        raise ValueError("Unsupported inspection image shape.")

    try:
        success, encoded = cv2.imencode(".png", image)
    except cv2.error as exc:
        raise ValueError(
            f"Could not encode inspection image: {exc}"
        ) from exc

    if not success:
        raise ValueError("Could not encode inspection image.")

    return assess_image_quality(encoded.tobytes())


def inspect_angle(
    angle: str,
    initial_image: np.ndarray,
    final_image: np.ndarray,
) -> AngleInspectionResult:
    """
    Compare one INITIAL and FINAL inspection image.

    Workflow:
    1. Validate image quality.
    2. Preprocess images.
    3. Align images.
    4. Calculate SSIM.
    5. Detect potential difference regions.
    """

    if not isinstance(angle, str):
        raise ValueError("Inspection angle must be a string.")

    angle = angle.strip().upper()

    if angle not in REQUIRED_ANGLES:
        raise ValueError(f"Unsupported inspection angle: {angle}")

    # Step 1: Assess both original images.
    initial_quality = _assess_array_quality(initial_image)
    final_quality = _assess_array_quality(final_image)

    quality_warnings = (
        [
            f"INITIAL: {warning}"
            for warning in initial_quality.warnings
        ]
        +
        [
            f"FINAL: {warning}"
            for warning in final_quality.warnings
        ]
    )

    # Step 2: Preprocess both images.
    initial_processed = preprocess_image(initial_image)
    final_processed = preprocess_image(final_image)

    # Step 3: Align FINAL image with INITIAL image.
    alignment = align_images(
        initial_processed,
        final_processed,
    )

    if not alignment.success:
        return AngleInspectionResult(
            angle=angle,
            status="FAILED",
            similarity_score=None,
            difference_percentage=None,
            potential_regions=[],
            review_required=True,
            message=(
                alignment.reason
                or "Image alignment failed."
            ),
            quality_warnings=quality_warnings,
        )

    # Step 4: Compare aligned images.
    comparison = compare_images(
    initial_processed,
    alignment.aligned_image,
    valid_mask=alignment.valid_mask,
    )

    # Step 5: Build result.
    review_required = (
        comparison.difference_percentage > 0
        or bool(quality_warnings)
    )

    message = "Comparison completed."

    if review_required:
        message += " Human review is recommended."

    if quality_warnings:
        message += " Image quality warnings detected."

    return AngleInspectionResult(
        angle=angle,
        status="COMPLETED",
        similarity_score=comparison.similarity_score,
        difference_percentage=comparison.difference_percentage,
        potential_regions=comparison.potential_regions,
        review_required=review_required,
        message=message,
        quality_warnings=quality_warnings,
    )


def inspect_all_angles(
    initial_images: dict[str, np.ndarray],
    final_images: dict[str, np.ndarray],
) -> InspectionResult:
    """
    Compare all six required inspection angles.

    Supports case-insensitive angle keys.
    Missing images and failed comparisons are reported explicitly.
    """

    if not isinstance(initial_images, dict):
        raise TypeError("initial_images must be a dictionary.")

    if not isinstance(final_images, dict):
        raise TypeError("final_images must be a dictionary.")

    # Validate supplied angle names.
    angle_validation = validate_angles(
        list(initial_images.keys())
    )

    final_validation = validate_angles(
        list(final_images.keys())
    )

    if angle_validation.duplicates or final_validation.duplicates:
        raise ValueError("Duplicate inspection angles are not allowed.")

    invalid_angles = (
        angle_validation.invalid
        + final_validation.invalid
    )

    if invalid_angles:
        raise ValueError(
            f"Invalid inspection angles: {invalid_angles}"
        )

    # Normalize angle keys.
    normalized_initial = {
        key.strip().upper(): value
        for key, value in initial_images.items()
    }

    normalized_final = {
        key.strip().upper(): value
        for key, value in final_images.items()
    }

    results: dict[str, AngleInspectionResult] = {}
    failed_angles = []

    # Process all six required angles independently.
    for angle in REQUIRED_ANGLES:

        initial_image = normalized_initial.get(angle)
        final_image = normalized_final.get(angle)

        # Handle missing images.
        if initial_image is None or final_image is None:

            results[angle] = AngleInspectionResult(
                angle=angle,
                status="MISSING",
                similarity_score=None,
                difference_percentage=None,
                potential_regions=[],
                review_required=True,
                message="Initial or final image is missing.",
                quality_warnings=[],
            )

            failed_angles.append(angle)
            continue

        # Handle failures independently for each angle.
        try:
            result = inspect_angle(
                angle,
                initial_image,
                final_image,
            )

        except (ValueError, TypeError, cv2.error) as exc:

            result = AngleInspectionResult(
                angle=angle,
                status="FAILED",
                similarity_score=None,
                difference_percentage=None,
                potential_regions=[],
                review_required=True,
                message=str(exc),
                quality_warnings=[],
            )

        results[angle] = result

        if result.status != "COMPLETED":
            failed_angles.append(angle)

    # Calculate overall score using completed angles only.
    completed = [
        result
        for result in results.values()
        if result.status == "COMPLETED"
    ]

    overall_score = None

    if completed:
        overall_score = round(
            sum(
                result.similarity_score
                for result in completed
            )
            / len(completed),
            2,
        )

    # Final inspection summary.
    return InspectionResult(
        status=(
            "COMPLETED"
            if not failed_angles
            else "PARTIAL"
        ),
        total_angles=len(REQUIRED_ANGLES),
        completed_angles=len(completed),
        failed_angles=failed_angles,
        angles=results,
        overall_similarity_score=overall_score,
        review_required=(
            bool(failed_angles)
            or any(
                result.review_required
                for result in results.values()
            )
        ),
    )