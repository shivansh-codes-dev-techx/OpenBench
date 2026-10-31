
from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

from cv_engine.preprocessing import convert_to_grayscale


@dataclass
class AlignmentResult:
    success: bool
    aligned_image: np.ndarray | None
    valid_mask: np.ndarray | None
    keypoints_reference: int
    keypoints_target: int
    good_matches: int
    inliers: int
    reason: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("aligned_image")
        data.pop("valid_mask")
        return data


def align_images(
    reference_image: np.ndarray,
    target_image: np.ndarray,
    *,
    min_matches: int = 10,
    min_inliers: int = 8,
    ratio_threshold: float = 0.75,
) -> AlignmentResult:
    """
    Align target_image to reference_image using ORB and homography.

    Returns:
    - aligned_image: warped target image
    - valid_mask: pixels belonging to the overlapping image area
    """

    if min_matches < 4 or min_inliers < 4:
        raise ValueError(
            "Match and inlier thresholds must be at least 4."
        )

    if not 0 < ratio_threshold < 1:
        raise ValueError(
            "ratio_threshold must be between 0 and 1."
        )

    try:
        reference_gray = convert_to_grayscale(reference_image)
        target_gray = convert_to_grayscale(target_image)

    except ValueError as exc:
        raise ValueError(f"Invalid input image: {exc}") from exc

    orb = cv2.ORB_create(nfeatures=3000)

    keypoints_ref, descriptors_ref = orb.detectAndCompute(
        reference_gray, None
    )

    keypoints_target, descriptors_target = orb.detectAndCompute(
        target_gray, None
    )

    ref_count = len(keypoints_ref)
    target_count = len(keypoints_target)

    def failure(reason: str, matches: int = 0) -> AlignmentResult:
        return AlignmentResult(
            success=False,
            aligned_image=None,
            valid_mask=None,
            keypoints_reference=ref_count,
            keypoints_target=target_count,
            good_matches=matches,
            inliers=0,
            reason=reason,
        )

    if descriptors_ref is None or descriptors_target is None:
        return failure("Insufficient visual features.")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

    pairs = matcher.knnMatch(
        descriptors_target,
        descriptors_ref,
        k=2,
    )

    good_matches = [
        first
        for pair in pairs
        if len(pair) == 2
        for first, second in [pair]
        if first.distance < ratio_threshold * second.distance
    ]

    if len(good_matches) < min_matches:
        return failure(
            "Not enough reliable feature matches.",
            len(good_matches),
        )

    target_points = np.float32([
        keypoints_target[match.queryIdx].pt
        for match in good_matches
    ]).reshape(-1, 1, 2)

    reference_points = np.float32([
        keypoints_ref[match.trainIdx].pt
        for match in good_matches
    ]).reshape(-1, 1, 2)

    homography, mask = cv2.findHomography(
        target_points,
        reference_points,
        cv2.RANSAC,
        5.0,
    )

    if homography is None or mask is None:
        return failure(
            "Could not calculate a reliable homography.",
            len(good_matches),
        )

    inliers = int(mask.ravel().sum())

    if inliers < min_inliers:
        return AlignmentResult(
            success=False,
            aligned_image=None,
            valid_mask=None,
            keypoints_reference=ref_count,
            keypoints_target=target_count,
            good_matches=len(good_matches),
            inliers=inliers,
            reason="Insufficient geometric agreement between images.",
        )

    height, width = reference_gray.shape

    aligned = cv2.warpPerspective(
        target_image,
        homography,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
    )

    # Create a mask representing the original target image area.
    source_mask = np.full(
        target_gray.shape,
        255,
        dtype=np.uint8,
    )

    valid_mask = cv2.warpPerspective(
        source_mask,
        homography,
        (width, height),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    return AlignmentResult(
        success=True,
        aligned_image=aligned,
        valid_mask=valid_mask,
        keypoints_reference=ref_count,
        keypoints_target=target_count,
        good_matches=len(good_matches),
        inliers=inliers,
    )