from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from cv_engine.angles import REQUIRED_ANGLES
from app.services.inspection_comparison_service import (
    compare_inspection_stages,
    decode_image_bytes,
)


def _image_bytes(value: int = 80) -> bytes:
    image = np.full((32, 32, 3), value, dtype=np.uint8)
    success, encoded = cv2.imencode(".png", image)
    assert success
    return encoded.tobytes()


def _image_set(value: int = 80) -> dict[str, bytes]:
    return {angle: _image_bytes(value) for angle in REQUIRED_ANGLES}


def _engine_result(*, failed_angle: str | None = None):
    angles = {}
    for angle in REQUIRED_ANGLES:
        failed = angle == failed_angle
        angles[angle] = {
            "angle": angle,
            "status": "FAILED" if failed else "COMPLETED",
            "similarity_score": None if failed else 91.25,
            "difference_percentage": None if failed else 2.5,
            "potential_regions": [] if failed else [
                {"x": 1, "y": 2, "width": 3, "height": 4, "area": 12}
            ],
            "review_required": True,
            "message": "Alignment failed." if failed else "Comparison completed.",
            "quality_warnings": ["Low resolution"] if not failed else [],
        }

    return SimpleNamespace(
        to_dict=lambda: {
            "status": "PARTIAL" if failed_angle else "COMPLETED",
            "total_angles": len(REQUIRED_ANGLES),
            "completed_angles": len(REQUIRED_ANGLES) - bool(failed_angle),
            "failed_angles": [failed_angle] if failed_angle else [],
            "angles": angles,
            "overall_similarity_score": 91.25,
            "review_required": True,
            "attention_required": True,
            "overall_score_status": (
                "PARTIAL" if failed_angle else "COMPLETE"
            ),
        }
    )


def test_decodes_stored_bytes_to_opencv_bgr_array():
    image = decode_image_bytes(_image_bytes())

    assert isinstance(image, np.ndarray)
    assert image.dtype == np.uint8
    assert image.shape == (32, 32, 3)


@pytest.mark.parametrize("image_data", [b"", b"not an image"])
def test_invalid_image_bytes_are_rejected(image_data):
    with pytest.raises(ValueError, match="Image"):
        decode_image_bytes(image_data)


def test_runs_all_three_comparisons_and_preserves_engine_results(monkeypatch):
    calls = []

    def fake_inspect_all_angles(reference, target):
        calls.append((reference, target))
        return _engine_result()

    monkeypatch.setattr(
        "app.services.inspection_comparison_service.inspect_all_angles",
        fake_inspect_all_angles,
    )

    result = compare_inspection_stages(
        _image_set(20),
        _image_set(80),
        _image_set(140),
    )

    assert len(calls) == 3
    assert result["status"] == "COMPLETED"
    assert result["completed_comparisons"] == 3
    assert result["failed_comparisons"] == []
    assert set(result["comparisons"]) == {
        "baseline_vs_initial",
        "initial_vs_final",
        "baseline_vs_final",
    }

    baseline_initial = result["comparisons"]["baseline_vs_initial"]
    assert baseline_initial["completed_angles"] == 6
    assert baseline_initial["failed_angles"] == []
    assert baseline_initial["angles"]["FRONT"]["similarity_score"] == 91.25
    assert baseline_initial["angles"]["FRONT"]["difference_percentage"] == 2.5
    assert baseline_initial["angles"]["FRONT"]["potential_regions"]
    assert baseline_initial["angles"]["FRONT"]["quality_warnings"]
    assert baseline_initial["review_required"] is True
    assert baseline_initial["attention_required"] is True
    assert baseline_initial["manual_review_required"] is True
    assert baseline_initial["overall_score_status"] == "COMPLETE"
    assert baseline_initial["overall_status"] == "COMPLETE"
    assert result["overall_status"] == "COMPLETE"
    assert result["manual_review_required"] is True


def test_missing_images_produce_partial_results_without_scores():
    result = compare_inspection_stages({}, {}, {})

    assert result["status"] == "PARTIAL"
    assert result["overall_status"] == "UNAVAILABLE"
    assert result["failed_comparisons"] == [
        "baseline_vs_initial",
        "initial_vs_final",
        "baseline_vs_final",
    ]
    for comparison in result["comparisons"].values():
        assert comparison["completed_angles"] == 0
        assert comparison["failed_angles"] == list(REQUIRED_ANGLES)
        assert comparison["overall_similarity_score"] is None
        assert comparison["overall_score_status"] == "UNAVAILABLE"
        assert comparison["overall_status"] == "UNAVAILABLE"
        assert comparison["angles"]["FRONT"]["status"] == "MISSING"
        assert comparison["missing_angles"] == list(REQUIRED_ANGLES)
        assert comparison["review_required"] is True
        assert comparison["attention_required"] is True


def test_invalid_image_is_reported_as_failed_angle(monkeypatch):
    monkeypatch.setattr(
        "app.services.inspection_comparison_service.inspect_all_angles",
        lambda reference, target: _engine_result(),
    )
    baseline = _image_set()
    baseline["FRONT"] = b"corrupt image"

    result = compare_inspection_stages(baseline, _image_set(), _image_set())
    comparison = result["comparisons"]["baseline_vs_initial"]

    assert comparison["status"] == "PARTIAL"
    assert comparison["overall_status"] == "PARTIAL"
    assert result["overall_status"] == "PARTIAL"
    assert comparison["angles"]["FRONT"]["status"] == "FAILED"
    assert comparison["angles"]["FRONT"]["similarity_score"] is None
    assert "baseline:" in comparison["angles"]["FRONT"]["message"]
    assert "FRONT" in comparison["failed_angles"]


def test_alignment_failure_is_preserved_and_requires_review(monkeypatch):
    monkeypatch.setattr(
        "app.services.inspection_comparison_service.inspect_all_angles",
        lambda reference, target: _engine_result(failed_angle="LEFT"),
    )

    result = compare_inspection_stages(_image_set(), _image_set(), _image_set())
    comparison = result["comparisons"]["baseline_vs_initial"]

    assert comparison["status"] == "PARTIAL"
    assert comparison["angles"]["LEFT"]["status"] == "FAILED"
    assert comparison["angles"]["LEFT"]["message"] == "Alignment failed."
    assert comparison["failed_angles"] == ["LEFT"]
    assert comparison["review_required"] is True
    assert comparison["overall_score_status"] == "PARTIAL"


def test_unexpected_decoder_error_is_local_to_one_angle(monkeypatch):
    from app.services import inspection_comparison_service as service

    def decoder(image_data):
        if image_data == b"unexpected-decoder-error":
            raise RuntimeError("decoder defect")
        return np.zeros((32, 32, 3), dtype=np.uint8)

    monkeypatch.setattr(service, "decode_image_bytes", decoder)
    monkeypatch.setattr(
        service,
        "inspect_all_angles",
        lambda reference, target: _engine_result(),
    )
    baseline = _image_set()
    baseline["FRONT"] = b"unexpected-decoder-error"

    result = service.compare_inspection_stages(
        baseline,
        _image_set(),
        _image_set(),
    )
    comparison = result["comparisons"]["baseline_vs_initial"]

    assert comparison["status"] == "PARTIAL"
    assert comparison["angles"]["FRONT"]["status"] == "FAILED"
    assert "RuntimeError: decoder defect" in comparison["angles"]["FRONT"]["message"]
    assert comparison["angles"]["BACK"]["status"] == "COMPLETED"
    assert "FRONT" in comparison["failed_angles"]
