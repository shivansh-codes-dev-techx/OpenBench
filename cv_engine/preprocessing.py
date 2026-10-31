from __future__ import annotations

import cv2
import numpy as np


class ImagePreprocessingError(ValueError):
    """Raised when image preprocessing receives invalid input."""


def _validate_image(image: np.ndarray) -> None:
    if not isinstance(image, np.ndarray):
        raise ImagePreprocessingError("Input must be a NumPy array.")

    if image.size == 0:
        raise ImagePreprocessingError("Input image is empty.")

    if image.dtype != np.uint8:
        raise ImagePreprocessingError("Image must have uint8 data type.")

    if image.ndim not in (2, 3):
        raise ImagePreprocessingError("Image must be grayscale or RGB/BGR.")

    if image.ndim == 3 and image.shape[2] not in (3, 4):
        raise ImagePreprocessingError("Image must have 3 or 4 channels.")


def resize_image(
    image: np.ndarray,
    width: int = 1280,
    height: int = 960,
) -> np.ndarray:
    """Resize an image to the requested dimensions."""

    _validate_image(image)

    if width <= 0 or height <= 0:
        raise ImagePreprocessingError(
            "Width and height must be positive."
        )

    return cv2.resize(
        image,
        (width, height),
        interpolation=cv2.INTER_AREA,
    )


def convert_to_grayscale(image: np.ndarray) -> np.ndarray:
    """Convert a grayscale, BGR or BGRA image to grayscale."""

    _validate_image(image)

    if image.ndim == 2:
        return image.copy()

    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)

    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def normalize_lighting(image: np.ndarray) -> np.ndarray:
    """Normalize local lighting using CLAHE."""

    gray = convert_to_grayscale(image)

    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8),
    )

    return clahe.apply(gray)


def preprocess_image(
    image: np.ndarray,
    width: int = 1280,
    height: int = 960,
) -> np.ndarray:
    """
    Resize, convert to grayscale and normalize lighting.

    Returns a standardized grayscale image.
    """

    resized = resize_image(image, width, height)
    return normalize_lighting(resized)
