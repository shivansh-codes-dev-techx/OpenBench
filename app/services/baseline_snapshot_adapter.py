"""Adapt database snapshot records to the CV provider's input contract."""

from collections.abc import Iterable

from app.models.booking_baseline_snapshot import BookingBaselineSnapshotImage
from cv_engine.angles import REQUIRED_ANGLES


def snapshot_records_to_angle_bytes(
    images: Iterable[BookingBaselineSnapshotImage],
) -> dict[str, bytes]:
    """Return the six frozen image payloads keyed by canonical angle name.

    Database access, authorization, and digest verification stay in the snapshot
    service. This adapter only converts its rows to the provider-facing shape.
    """
    result: dict[str, bytes] = {}
    for image in images:
        angle = image.angle.strip().upper()
        if angle not in REQUIRED_ANGLES:
            raise ValueError(f"Unsupported snapshot angle: {image.angle}")
        if angle in result:
            raise ValueError(f"Duplicate snapshot angle: {angle}")
        result[angle] = bytes(image.image_data)

    missing = [angle for angle in REQUIRED_ANGLES if angle not in result]
    if missing:
        raise ValueError("Snapshot is missing required angles: " + ", ".join(missing))
    return result
