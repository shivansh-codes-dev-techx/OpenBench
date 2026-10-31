import cv2
import numpy as np
import pytest

from cv_engine.alignment import align_images
def create_test_image():
    rng = np.random.default_rng(42)

    image = rng.integers(
        0, 256,
        (400, 400, 3),
        dtype=np.uint8
    )

    return image

@pytest.fixture
def textured_image():
    rng = np.random.default_rng(42)

    image = rng.integers(
        0, 256,
        size=(480, 640, 3),
        dtype=np.uint8,
    )

    for x in range(40, 600, 80):
        cv2.rectangle(image, (x, 50), (x + 35, 100), (255, 255, 255), 2)

    return image


def test_identical_images_align_successfully(textured_image):
    result = align_images(textured_image, textured_image)

    assert result.success is True
    assert result.aligned_image is not None
    assert result.inliers >= 8


def test_translated_image_aligns(textured_image):
    matrix = np.float32([
        [1, 0, 12],
        [0, 1, 8],
    ])

    shifted = cv2.warpAffine(
        textured_image,
        matrix,
        (640, 480),
    )

    result = align_images(textured_image, shifted)

    assert result.success is True
    assert result.aligned_image.shape == textured_image.shape


def test_blank_images_fail_gracefully():
    image = np.zeros((480, 640, 3), dtype=np.uint8)

    result = align_images(image, image)

    assert result.success is False
    assert result.aligned_image is None
    assert result.reason is not None


def test_insufficient_matches_fail_gracefully():
    reference = np.zeros((480, 640, 3), dtype=np.uint8)

    target = np.random.default_rng(10).integers(
        0, 256,
        size=(480, 640, 3),
        dtype=np.uint8,
    )

    result = align_images(reference, target)

    assert result.success is False
    assert result.aligned_image is None


def test_invalid_threshold_is_rejected(textured_image):
    with pytest.raises(ValueError):
        align_images(
            textured_image,
            textured_image,
            min_matches=2,
        )


def test_invalid_ratio_is_rejected(textured_image):
    with pytest.raises(ValueError):
        align_images(
            textured_image,
            textured_image,
            ratio_threshold=1.5,
        )


def test_result_dictionary_excludes_image_data(textured_image):
    result = align_images(textured_image, textured_image)

    data = result.to_dict()

    assert "success" in data
    assert "aligned_image" not in data

def test_alignment_returns_valid_mask():
    image = create_test_image()

    result = align_images(image, image.copy())

    assert result.success is True
    assert result.valid_mask is not None
    assert result.valid_mask.shape == image.shape[:2]
    assert result.valid_mask.dtype == np.uint8


def test_valid_mask_contains_valid_pixels():
    image = create_test_image()

    result = align_images(image, image.copy())

    assert np.count_nonzero(result.valid_mask) > 0


def test_alignment_dict_excludes_image_and_mask():
    image = create_test_image()

    result = align_images(image, image.copy())
    data = result.to_dict()

    assert "aligned_image" not in data
    assert "valid_mask" not in data