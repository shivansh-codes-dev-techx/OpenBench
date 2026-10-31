import cv2
import numpy as np
import pytest

from cv_engine.preprocessing import (
    ImagePreprocessingError,
    resize_image,
    convert_to_grayscale,
    normalize_lighting,
    preprocess_image,
)


@pytest.fixture
def sample_image():
    return np.full((480, 640, 3), 120, dtype=np.uint8)


def test_resize_image(sample_image):
    result = resize_image(sample_image, 320, 240)

    assert result.shape == (240, 320, 3)


def test_resize_rejects_invalid_dimensions(sample_image):
    with pytest.raises(ImagePreprocessingError):
        resize_image(sample_image, 0, 240)


def test_grayscale_conversion(sample_image):
    result = convert_to_grayscale(sample_image)

    assert result.shape == (480, 640)
    assert result.dtype == np.uint8


def test_grayscale_input_is_supported():
    image = np.full((100, 100), 120, dtype=np.uint8)

    result = convert_to_grayscale(image)

    assert np.array_equal(result, image)


def test_bgra_image_is_supported():
    image = np.full((100, 100, 4), 120, dtype=np.uint8)

    result = convert_to_grayscale(image)

    assert result.shape == (100, 100)


def test_lighting_normalization_returns_grayscale(sample_image):
    result = normalize_lighting(sample_image)

    assert result.shape == (480, 640)
    assert result.dtype == np.uint8


def test_complete_preprocessing_pipeline(sample_image):
    result = preprocess_image(sample_image, 320, 240)

    assert result.shape == (240, 320)
    assert result.dtype == np.uint8


def test_empty_image_is_rejected():
    with pytest.raises(ImagePreprocessingError):
        resize_image(np.array([]))


def test_non_numpy_input_is_rejected():
    with pytest.raises(ImagePreprocessingError):
        convert_to_grayscale([1, 2, 3])
