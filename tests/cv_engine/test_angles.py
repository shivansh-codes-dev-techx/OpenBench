import pytest

from cv_engine.angles import REQUIRED_ANGLES, validate_angles


def test_all_six_angles_are_valid():
    result = validate_angles(list(REQUIRED_ANGLES))

    assert result.valid is True
    assert result.missing == []
    assert result.duplicates == []
    assert result.invalid == []


def test_missing_angles_are_detected():
    result = validate_angles(["FRONT", "BACK", "LEFT"])

    assert result.valid is False
    assert result.missing == ["RIGHT", "TOP", "BOTTOM"]


def test_duplicate_angles_are_detected():
    result = validate_angles([
        "FRONT", "FRONT", "BACK", "LEFT",
        "RIGHT", "TOP", "BOTTOM"
    ])

    assert result.valid is False
    assert result.duplicates == ["FRONT"]


def test_invalid_angles_are_detected():
    result = validate_angles([
        "FRONT", "BACK", "LEFT",
        "RIGHT", "TOP", "BOTTOM", "DIAGONAL"
    ])

    assert result.valid is False
    assert result.invalid == ["DIAGONAL"]


def test_angle_matching_is_case_insensitive():
    result = validate_angles([
        "front", "back", "left",
        "right", "top", "bottom"
    ])

    assert result.valid is True


def test_whitespace_is_ignored():
    result = validate_angles([
        " FRONT ", " BACK ", " LEFT ",
        " RIGHT ", " TOP ", " BOTTOM "
    ])

    assert result.valid is True


def test_non_string_angle_is_invalid():
    result = validate_angles([
        "FRONT", "BACK", "LEFT",
        "RIGHT", "TOP", "BOTTOM", 123
    ])

    assert result.valid is False
    assert result.invalid == ["123"]


def test_non_list_input_is_rejected():
    with pytest.raises(TypeError):
        validate_angles("FRONT")


def test_result_can_be_converted_to_dictionary():
    result = validate_angles(list(REQUIRED_ANGLES))

    data = result.to_dict()

    assert data["valid"] is True
    assert len(data["present"]) == 6
