from io import BytesIO

import pytest
import numpy as np
from PIL import Image

from cv_engine.quality import (
    ImageValidationError,
    assess_image_quality,
    assess_image_array_quality,
)


def make_test_image(color=(120, 120, 120), size=(640, 480)):
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_valid_image_returns_quality_metrics():
    result = assess_image_quality(make_test_image())

    assert result.valid is True
    assert result.image_format == "JPEG"
    assert result.width == 640
    assert result.height == 480
    assert result.file_size_bytes > 0
    assert isinstance(result.blur_variance, float)
    assert isinstance(result.warnings, list)


def test_empty_image_is_rejected():
    with pytest.raises(ImageValidationError):
        assess_image_quality(b"")


def test_corrupt_image_is_rejected():
    with pytest.raises(ImageValidationError):
        assess_image_quality(b"not-an-image")


def test_small_image_generates_resolution_warning():
    image_bytes = make_test_image(size=(100, 100))
    result = assess_image_quality(image_bytes)

    assert any("Low resolution" in warning for warning in result.warnings)


def test_dark_image_generates_exposure_warning():
    image_bytes = make_test_image(color=(5, 5, 5))
    result = assess_image_quality(image_bytes)

    assert any("dark-region" in warning for warning in result.warnings)


def test_result_can_be_converted_to_dictionary():
    result = assess_image_quality(make_test_image())

    data = result.to_dict()

    assert data["valid"] is True
    assert "blur_variance" in data


def test_decoded_array_quality_does_not_reencode_or_apply_file_size_limit():
    image = np.random.default_rng(15).integers(
        0, 256, size=(2400, 3200, 3), dtype=np.uint8
    )

    result = assess_image_array_quality(image)

    assert result.valid is True
    assert result.image_format == "DECODED_ARRAY"
    assert (result.width, result.height) == (3200, 2400)
    assert result.file_size_bytes == 0


def test_decoded_array_quality_rejects_more_than_40_megapixels():
    image = np.zeros((5000, 8001), dtype=np.uint8)

    with pytest.raises(ImageValidationError, match="40 megapixel"):
        assess_image_array_quality(image)
