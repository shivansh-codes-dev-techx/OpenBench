
import cv2
import numpy as np
import pytest
from types import SimpleNamespace
from cv_engine.angles import REQUIRED_ANGLES
from cv_engine.inspection import (
    inspect_all_angles,
    inspect_angle,
)


@pytest.fixture
def inspection_images():
    rng = np.random.default_rng(42)

    initial = rng.integers(
        30,
        220,
        size=(400, 400, 3),
        dtype=np.uint8,
    )

    final = initial.copy()

    # Add a visible changed region.
    cv2.rectangle(
        final,
        (150, 150),
        (220, 220),
        (255, 255, 255),
        -1,
    )

    initial_images = {
        angle: initial.copy()
        for angle in REQUIRED_ANGLES
    }

    final_images = {
        angle: final.copy()
        for angle in REQUIRED_ANGLES
    }

    return initial_images, final_images


def test_all_six_angles_are_processed(inspection_images):
    initial, final = inspection_images

    result = inspect_all_angles(initial, final)

    assert result.total_angles == 6
    assert result.completed_angles == 6
    assert result.status == "COMPLETED"
    assert result.failed_angles == []


def test_missing_angle_is_reported(inspection_images):
    initial, final = inspection_images

    del initial["TOP"]

    result = inspect_all_angles(initial, final)

    assert result.status == "PARTIAL"
    assert "TOP" in result.failed_angles
    assert result.angles["TOP"].status == "MISSING"


def test_missing_final_image_is_reported(inspection_images):
    initial, final = inspection_images

    del final["BOTTOM"]

    result = inspect_all_angles(initial, final)

    assert result.angles["BOTTOM"].status == "MISSING"


def test_changed_region_requires_review(inspection_images):
    initial, final = inspection_images

    result = inspect_all_angles(initial, final)

    assert result.review_required is True
    assert result.angles["FRONT"].review_required is True


def test_identical_images_have_high_similarity():
    rng = np.random.default_rng(42)

    image = rng.integers(
        30,
        220,
        size=(400, 400, 3),
        dtype=np.uint8,
    )

    result = inspect_angle("FRONT", image, image.copy())

    assert result.status == "COMPLETED"
    assert result.similarity_score == pytest.approx(100.0)


def test_invalid_angle_is_rejected():
    image = np.zeros((400, 400, 3), dtype=np.uint8)

    with pytest.raises(ValueError):
        inspect_angle("DIAGONAL", image, image)


def test_duplicate_angles_are_rejected(inspection_images):
    initial, final = inspection_images

    initial["FRONT_DUPLICATE"] = initial["FRONT"]

    with pytest.raises(ValueError):
        inspect_all_angles(initial, final)


def test_overall_score_is_none_when_nothing_completes():
    result = inspect_all_angles({}, {})

    assert result.completed_angles == 0
    assert result.overall_similarity_score is None
    assert result.overall_score_status == "UNAVAILABLE"
    assert result.status == "PARTIAL"
    assert result.manual_review_required is True
    assert result.attention_required is True


def test_result_dictionary_is_serializable(inspection_images):
    initial, final = inspection_images

    result = inspect_all_angles(initial, final)
    data = result.to_dict()

    assert data["total_angles"] == 6
    assert "FRONT" in data["angles"]
    assert "overall_similarity_score" in data
    assert data["overall_score_status"] == "COMPLETE"
    assert data["manual_review_required"] is True
    assert "attention_required" in data

def test_lowercase_angle_keys_are_supported(inspection_images):
    initial, final = inspection_images

    lowercase_initial = {
        angle.lower(): image
        for angle, image in initial.items()
    }

    lowercase_final = {
        angle.lower(): image
        for angle, image in final.items()
    }

    result = inspect_all_angles(
        lowercase_initial,
        lowercase_final,
    )

    assert result.status == "COMPLETED"
    assert result.completed_angles == 6
    assert result.failed_angles == []

def test_quality_warnings_are_included_in_result():
    from cv_engine.inspection import inspect_angle

    rng = np.random.default_rng(42)
    image = rng.integers(
        30, 220, (400, 400, 3), dtype=np.uint8
    )

    result = inspect_angle("FRONT", image, image.copy())

    assert isinstance(result.quality_warnings, list)
    assert "quality_warnings" in result.to_dict()


def test_low_resolution_image_generates_quality_warning():
    from cv_engine.inspection import inspect_angle

    rng = np.random.default_rng(42)
    image = rng.integers(
        30, 220, (200, 200, 3), dtype=np.uint8
    )

    result = inspect_angle("FRONT", image, image.copy())

    assert result.review_required is True
    assert result.attention_required is True
    assert result.manual_review_required is True
    assert len(result.quality_warnings) > 0


def test_one_failed_angle_does_not_stop_other_angles(inspection_images):
    initial, final = inspection_images

    # Invalid dtype should fail only this angle.
    initial["LEFT"] = np.zeros(
        (400, 400, 3),
        dtype=np.float32,
    )

    result = inspect_all_angles(initial, final)

    assert result.status == "PARTIAL"
    assert result.completed_angles == 5
    assert result.overall_score_status == "PARTIAL"
    assert result.overall_similarity_score is not None
    assert result.angles["LEFT"].status == "FAILED"
    assert result.failed_angles == ["LEFT"]


def test_only_changed_angle_requires_review(inspection_images):
    initial, final = inspection_images

    # Make all final images identical to their initial versions.
    final = {
        angle: image.copy()
        for angle, image in initial.items()
    }

    # Introduce a change only in FRONT.
    cv2.rectangle(
        final["FRONT"],
        (150, 150),
        (220, 220),
        (255, 255, 255),
        -1,
    )

    result = inspect_all_angles(initial, final)

    assert result.completed_angles == 6
    assert result.status == "COMPLETED"
    assert result.angles["FRONT"].review_required is True
    assert result.angles["FRONT"].attention_required is True
    assert result.angles["FRONT"].manual_review_required is True

    for angle in REQUIRED_ANGLES:
        if angle != "FRONT":
            assert result.angles[angle].review_required is False
            assert result.angles[angle].attention_required is False
            assert result.angles[angle].manual_review_required is True
    assert result.manual_review_required is True


def test_identical_good_quality_images_still_require_manual_review():
    rng = np.random.default_rng(42)
    image = rng.integers(30, 220, (400, 400, 3), dtype=np.uint8)

    result = inspect_angle("FRONT", image, image.copy())

    assert result.attention_required is False
    assert result.manual_review_required is True
    assert result.to_dict()["manual_review_required"] is True


def test_grayscale_images_are_supported():
    rng = np.random.default_rng(43)
    image = rng.integers(30, 220, (400, 400), dtype=np.uint8)

    result = inspect_angle("FRONT", image, image.copy())

    assert result.status == "COMPLETED"
    assert result.similarity_score == pytest.approx(100.0)
    assert result.manual_review_required is True


def test_four_channel_images_are_supported():
    rng = np.random.default_rng(44)
    rgb = rng.integers(30, 220, (400, 400, 3), dtype=np.uint8)
    alpha = np.full((400, 400, 1), 255, dtype=np.uint8)
    image = np.concatenate((rgb, alpha), axis=2)

    result = inspect_angle("FRONT", image, image.copy())

    assert result.status == "COMPLETED"
    assert result.similarity_score == pytest.approx(100.0)
    assert result.manual_review_required is True


@pytest.mark.parametrize(
    "invalid_image",
    [
        np.empty((0, 400, 3), dtype=np.uint8),
        np.zeros((400, 400, 5), dtype=np.uint8),
        np.zeros((400, 400, 3), dtype=np.float32),
    ],
)
def test_invalid_image_shapes_and_dtypes_fail_only_their_angle(
    inspection_images,
    invalid_image,
):
    initial, final = inspection_images
    initial["LEFT"] = invalid_image

    result = inspect_all_angles(initial, final)

    assert result.status == "PARTIAL"
    assert result.completed_angles == 5
    assert result.angles["LEFT"].status == "FAILED"
    assert result.angles["LEFT"].attention_required is True
    assert result.angles["LEFT"].manual_review_required is True
    assert "LEFT" in result.failed_angles


def test_non_string_angle_key_returns_controlled_validation_error(
    inspection_images,
):
    initial, final = inspection_images
    initial[42] = initial["FRONT"]

    with pytest.raises(ValueError, match="Invalid inspection angles"):
        inspect_all_angles(initial, final)


def test_alignment_failure_requires_manual_review_and_attention():
    image = np.zeros((400, 400, 3), dtype=np.uint8)

    result = inspect_angle("FRONT", image, image.copy())

    assert result.status == "FAILED"
    assert result.similarity_score is None
    assert result.attention_required is True
    assert result.manual_review_required is True


def test_unexpected_processing_error_is_not_silently_swallowed(
    inspection_images,
    monkeypatch,
):
    initial, final = inspection_images
    processed_angles = []

    def fail_unexpectedly(angle, initial_image, final_image):
        processed_angles.append(angle)
        if angle == "FRONT":
            raise RuntimeError("unexpected processing defect")
        raise ValueError("expected image validation failure")

    monkeypatch.setattr(
        "cv_engine.inspection.inspect_angle",
        fail_unexpectedly,
    )

    with pytest.raises(RuntimeError, match="unexpected processing defect"):
        inspect_all_angles(initial, final)

    assert processed_angles == ["FRONT"]


def test_inspection_passes_valid_mask_to_comparison(
    inspection_images,
    monkeypatch,
):
    initial, final = inspection_images

    expected_mask = np.full(
        (960, 1280),
        255,
        dtype=np.uint8,
    )

    def fake_align(reference_image, target_image, **kwargs):
        return SimpleNamespace(
            success=True,
            aligned_image=target_image,
            valid_mask=expected_mask,
            reason=None,
        )

    def fake_compare(
        reference_image,
        target_image,
        *,
        valid_mask=None,
        **kwargs,
    ):
        assert valid_mask is expected_mask

        return SimpleNamespace(
            similarity_score=100.0,
            difference_percentage=0.0,
            potential_regions=[],
        )

    monkeypatch.setattr(
        "cv_engine.inspection.align_images",
        fake_align,
    )

    monkeypatch.setattr(
        "cv_engine.inspection.compare_images",
        fake_compare,
    )

    result = inspect_angle(
        "FRONT",
        initial["FRONT"],
        final["FRONT"],
    )

    assert result.status == "COMPLETED"
    assert result.similarity_score == 100.0