from dataclasses import asdict, dataclass


REQUIRED_ANGLES = (
    "FRONT",
    "BACK",
    "LEFT",
    "RIGHT",
    "TOP",
    "BOTTOM",
)


@dataclass
class AngleValidationResult:
    valid: bool
    present: list[str]
    missing: list[str]
    duplicates: list[str]
    invalid: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def validate_angles(provided_angles: list[str]) -> AngleValidationResult:
    """
    Validate that all six required inspection angles are provided.

    Matching is case-insensitive and ignores surrounding whitespace.
    Duplicate angles are reported once in the duplicates list.
    """

    if not isinstance(provided_angles, (list, tuple)):
        raise TypeError("provided_angles must be a list or tuple.")

    present = []
    duplicates = []
    invalid = []
    seen = set()

    for angle in provided_angles:
        if not isinstance(angle, str):
            invalid.append(str(angle))
            continue

        normalized = angle.strip().upper()

        if normalized not in REQUIRED_ANGLES:
            invalid.append(angle)
            continue

        if normalized in seen:
            if normalized not in duplicates:
                duplicates.append(normalized)
            continue

        seen.add(normalized)
        present.append(normalized)

    missing = [
        angle for angle in REQUIRED_ANGLES
        if angle not in seen
    ]

    return AngleValidationResult(
        valid=not missing and not duplicates and not invalid,
        present=present,
        missing=missing,
        duplicates=duplicates,
        invalid=invalid,
    )
