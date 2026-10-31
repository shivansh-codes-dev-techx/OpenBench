from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_IMAGE_PIXELS = 40_000_000       # 40 megapixels
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}


class ImageValidationError(ValueError):
    """Raised when an inspection image is invalid or unsupported."""


@dataclass
class ImageQualityResult:
    valid: bool
    image_format: str
    width: int
    height: int
    file_size_bytes: int
    blur_variance: float
    brightness_mean: float
    underexposed_fraction: float
    overexposed_fraction: float
    warnings: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def assess_image_quality(
    image_bytes: bytes,
    *,
    min_dimension: int = 320,
    blur_threshold: float | None = None,
) -> ImageQualityResult:
    """
    Decode an inspection image and calculate basic quality metrics.

    The function is independent of FastAPI, SQLAlchemy and storage.
    Optional blur_threshold enables configurable blur warnings.
    """

    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ImageValidationError("Image data is empty or invalid.")

    file_size = len(image_bytes)

    if file_size > MAX_IMAGE_BYTES:
        raise ImageValidationError("Image exceeds the 15 MB size limit.")

    try:
        # Verify file integrity before fully decoding.
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = image.format

            if image_format not in SUPPORTED_FORMATS:
                raise ImageValidationError(
                    f"Unsupported image format: {image_format}."
                )

            width, height = image.size

            if width <= 0 or height <= 0:
                raise ImageValidationError("Invalid image dimensions.")

            if width * height > MAX_IMAGE_PIXELS:
                raise ImageValidationError(
                    "Image exceeds the 40 megapixel limit."
                )

            image.verify()

        # Reopen after verify() and decode into RGB.
        with Image.open(BytesIO(image_bytes)) as image:
            rgb_image = np.asarray(image.convert("RGB"))

    except ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageValidationError(
            "Image is corrupt or cannot be decoded."
        ) from exc

    if rgb_image.size == 0:
        raise ImageValidationError("Decoded image is empty.")

    gray_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)

    # Higher variance generally indicates more image detail.
    blur_variance = float(
        cv2.Laplacian(gray_image, cv2.CV_64F).var()
    )

    brightness_mean = float(np.mean(gray_image))

    underexposed_fraction = float(
        np.mean(gray_image < 30)
    )

    overexposed_fraction = float(
        np.mean(gray_image > 225)
    )

    warnings = []

    if min(width, height) < min_dimension:
        warnings.append(
            f"Low resolution: shortest dimension is below "
            f"{min_dimension}px."
        )

    if underexposed_fraction > 0.25:
        warnings.append("Significant dark-region exposure detected.")

    if overexposed_fraction > 0.25:
        warnings.append("Significant bright-region exposure detected.")

    if (
        blur_threshold is not None
        and blur_variance < blur_threshold
    ):
        warnings.append("Possible image blur detected.")

    return ImageQualityResult(
        valid=True,
        image_format=image_format,
        width=width,
        height=height,
        file_size_bytes=file_size,
        blur_variance=round(blur_variance, 3),
        brightness_mean=round(brightness_mean, 3),
        underexposed_fraction=round(underexposed_fraction, 4),
        overexposed_fraction=round(overexposed_fraction, 4),
        warnings=warnings,
    )
