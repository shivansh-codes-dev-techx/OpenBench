import numpy as np
import pytest

from cv_engine.comparison import compare_images


@pytest.fixture
def reference_image():
    rng = np.random.default_rng(42)

    return rng.integers(
        30,
        220,
        size=(256, 256, 3),
        dtype=np.uint8,
    )


def test_identical_images_have_high_similarity(reference_image):
    result = compare_images(reference_image, reference_image)

    assert result.similarity_score == pytest.approx(100.0)
    assert result.difference_percentage == 0.0
    assert result.potential_regions == []


def test_changed_region_is_detected(reference_image):
    changed = reference_image.copy()
    changed[80:150, 80:150] = 255

    result = compare_images(
        reference_image,
        changed,
        min_region_area=20,
    )

    assert result.similarity_score < 100
    assert result.difference_percentage > 0
    assert len(result.potential_regions) > 0


def test_difference_map_has_expected_dimensions(reference_image):
    result = compare_images(reference_image, reference_image)

    assert result.difference_map.shape == (256, 256)
    assert result.difference_map.dtype == np.uint8


def test_similarity_map_has_expected_dimensions(reference_image):
    result = compare_images(reference_image, reference_image)

    assert result.similarity_map.shape == (256, 256)


def test_different_dimensions_are_rejected(reference_image):
    smaller = reference_image[:128, :128]

    with pytest.raises(ValueError, match="identical dimensions"):
        compare_images(reference_image, smaller)


def test_invalid_difference_threshold_is_rejected(reference_image):
    with pytest.raises(ValueError):
        compare_images(
            reference_image,
            reference_image,
            difference_threshold=1.5,
        )


def test_invalid_region_area_is_rejected(reference_image):
    with pytest.raises(ValueError):
        compare_images(
            reference_image,
            reference_image,
            min_region_area=0,
        )


def test_tiny_images_are_rejected():
    image = np.zeros((5, 5), dtype=np.uint8)

    with pytest.raises(ValueError, match="at least 11x11"):
        compare_images(image, image)


def test_result_dictionary_excludes_image_arrays(reference_image):
    result = compare_images(reference_image, reference_image)

    data = result.to_dict()

    assert "similarity_score" in data
    assert "difference_percentage" in data
    assert "potential_regions" in data
    assert "difference_map" not in data
    assert "similarity_map" not in data

def test_valid_mask_excludes_invalid_border_pixels(reference_image):
    target = reference_image.copy()

    # Simulate black padding outside the valid overlap.
    target[:40, :] = 0
    target[-40:, :] = 0
    target[:, :40] = 0
    target[:, -40:] = 0

    valid_mask = np.zeros((256, 256), dtype=np.uint8)
    valid_mask[40:216, 40:216] = 255

    result = compare_images(
        reference_image,
        target,
        valid_mask=valid_mask,
    )

    assert result.similarity_score == pytest.approx(100.0)
    assert result.difference_percentage == 0.0
    assert result.potential_regions == []


def test_valid_mask_still_detects_changes_inside_overlap(reference_image):
    changed = reference_image.copy()
    changed[100:150, 100:150] = 255

    valid_mask = np.full((256, 256), 255, dtype=np.uint8)

    result = compare_images(
        reference_image,
        changed,
        valid_mask=valid_mask,
        min_region_area=20,
    )

    assert result.similarity_score < 100
    assert result.difference_percentage > 0
    assert len(result.potential_regions) > 0


def test_invalid_valid_mask_dimensions_are_rejected(reference_image):
    invalid_mask = np.ones((100, 100), dtype=np.uint8)

    with pytest.raises(ValueError, match="same dimensions"):
        compare_images(
            reference_image,
            reference_image,
            valid_mask=invalid_mask,
        )


def test_empty_valid_mask_is_rejected(reference_image):
    empty_mask = np.zeros((256, 256), dtype=np.uint8)

    with pytest.raises(ValueError, match="insufficient overlapping area"):
        compare_images(
            reference_image,
            reference_image,
            valid_mask=empty_mask,
        )