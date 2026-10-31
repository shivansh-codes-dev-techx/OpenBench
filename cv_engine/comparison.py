
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from cv_engine.preprocessing import convert_to_grayscale


@dataclass
class ComparisonResult:
    similarity_score: float
    difference_percentage: float
    potential_regions: list[dict]
    difference_map: np.ndarray
    similarity_map: np.ndarray

    def to_dict(self) -> dict:
        return {
            "similarity_score": self.similarity_score,
            "difference_percentage": self.difference_percentage,
            "potential_regions": self.potential_regions,
        }


def calculate_ssim(
    reference: np.ndarray,
    target: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Calculate SSIM using OpenCV without SciPy or scikit-image."""

    reference = reference.astype(np.float64)
    target = target.astype(np.float64)

    mu1 = cv2.GaussianBlur(reference, (11, 11), 1.5)
    mu2 = cv2.GaussianBlur(target, (11, 11), 1.5)

    mu1_sq = mu1 * mu1
    mu2_sq = mu2 * mu2
    mu1_mu2 = mu1 * mu2

    sigma1_sq = cv2.GaussianBlur(
        reference * reference, (11, 11), 1.5
    ) - mu1_sq

    sigma2_sq = cv2.GaussianBlur(
        target * target, (11, 11), 1.5
    ) - mu2_sq

    sigma12 = cv2.GaussianBlur(
        reference * target, (11, 11), 1.5
    ) - mu1_mu2

    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2

    numerator = (
        (2 * mu1_mu2 + c1)
        * (2 * sigma12 + c2)
    )

    denominator = (
        (mu1_sq + mu2_sq + c1)
        * (sigma1_sq + sigma2_sq + c2)
    )

    ssim_map = numerator / np.maximum(denominator, 1e-12)
    score = float(np.mean(ssim_map))

    return score, ssim_map


def compare_images(
    reference_image: np.ndarray,
    target_image: np.ndarray,
    *,
    valid_mask: np.ndarray | None = None,
    difference_threshold: float = 0.15,
    min_region_area: int = 100,
) -> ComparisonResult:
    """
    Compare two already-aligned images using SSIM.

    If valid_mask is supplied, only the overlapping image area
    is included in scoring and potential difference detection.
    """

    if not 0 < difference_threshold < 1:
        raise ValueError(
            "difference_threshold must be between 0 and 1."
        )

    if min_region_area < 1:
        raise ValueError("min_region_area must be positive.")

    try:
        reference_gray = convert_to_grayscale(reference_image)
        target_gray = convert_to_grayscale(target_image)

    except ValueError as exc:
        raise ValueError(f"Invalid input image: {exc}") from exc

    if reference_gray.shape != target_gray.shape:
        raise ValueError(
            "Images must have identical dimensions. Align them first."
        )

    height, width = reference_gray.shape

    if min(height, width) < 11:
        raise ValueError(
            "Images must be at least 11x11 pixels for SSIM."
        )

    comparison_mask = None

    if valid_mask is not None:
        if not isinstance(valid_mask, np.ndarray):
            raise ValueError("valid_mask must be a NumPy array.")

        if valid_mask.shape != reference_gray.shape:
            raise ValueError(
                "valid_mask must have the same dimensions as the images."
            )

        if valid_mask.dtype not in (np.uint8, np.bool_):
            raise ValueError(
                "valid_mask must have uint8 or bool data type."
            )

        binary_mask = (valid_mask > 0).astype(np.uint8)

        # SSIM uses an 11x11 window. Erosion excludes boundary
        # pixels whose SSIM window may include invalid border areas.
        kernel = np.ones((11, 11), dtype=np.uint8)

        comparison_mask = cv2.erode(
            binary_mask,
            kernel,
            iterations=1,
            borderType=cv2.BORDER_CONSTANT,
            borderValue=0,
        )

        if np.count_nonzero(comparison_mask) == 0:
            raise ValueError(
                "valid_mask has insufficient overlapping area for SSIM."
            )

    score, ssim_map = calculate_ssim(
        reference_gray,
        target_gray,
    )

    similarity_map = np.clip(ssim_map, -1.0, 1.0)

    difference_map = (
        (1.0 - similarity_map) * 127.5
    ).clip(0, 255).astype(np.uint8)

    pixel_threshold = int(difference_threshold * 255)

    _, difference_mask = cv2.threshold(
        difference_map,
        pixel_threshold,
        255,
        cv2.THRESH_BINARY,
    )

    kernel = np.ones((3, 3), dtype=np.uint8)

    difference_mask = cv2.morphologyEx(
        difference_mask,
        cv2.MORPH_OPEN,
        kernel,
    )

    difference_mask = cv2.morphologyEx(
        difference_mask,
        cv2.MORPH_CLOSE,
        kernel,
    )

    if comparison_mask is not None:
        # Exclude invalid pixels after morphology as well.
        difference_mask = cv2.bitwise_and(
            difference_mask,
            comparison_mask * 255,
        )

        valid_pixel_count = int(
            np.count_nonzero(comparison_mask)
        )

        score = float(
            np.mean(ssim_map[comparison_mask > 0])
        )

    else:
        valid_pixel_count = difference_mask.size

    difference_percentage = (
        np.count_nonzero(difference_mask)
        / valid_pixel_count
    ) * 100.0

    count, _, stats, _ = cv2.connectedComponentsWithStats(
        difference_mask,
        connectivity=8,
    )

    potential_regions = []

    for index in range(1, count):
        x, y, region_width, region_height, area = stats[index]

        if area < min_region_area:
            continue

        potential_regions.append({
            "x": int(x),
            "y": int(y),
            "width": int(region_width),
            "height": int(region_height),
            "area": int(area),
        })

    potential_regions.sort(
        key=lambda region: region["area"],
        reverse=True,
    )

    return ComparisonResult(
        similarity_score=round(
            float(np.clip(score, 0, 1) * 100), 2
        ),
        difference_percentage=round(
            float(difference_percentage), 2
        ),
        potential_regions=potential_regions,
        difference_map=difference_map,
        similarity_map=similarity_map,
    )