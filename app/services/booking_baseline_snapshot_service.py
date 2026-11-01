"""Create immutable, booking-specific copies of a resource's six baselines."""

import hashlib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.booking_baseline_snapshot import (
    BookingBaselineSnapshot,
    BookingBaselineSnapshotImage,
)
from app.models.enums import BookingStatus, UserRole
from app.models.resource import Resource
from app.models.resource_baseline_image import ResourceBaselineImage
from app.models.user import User
from cv_engine.angles import REQUIRED_ANGLES
from cv_engine.quality import ImageValidationError, assess_image_quality


class BookingBaselineSnapshotError(RuntimeError):
    """Base error for the booking-baseline snapshot service contract."""


class BookingNotFoundForSnapshotError(LookupError):
    pass


class SnapshotAccessDeniedError(PermissionError):
    pass


class SnapshotRequiresApprovedBookingError(BookingBaselineSnapshotError):
    pass


class IncompleteResourceBaselineError(BookingBaselineSnapshotError):
    def __init__(
        self,
        missing_angles: list[str],
        invalid_angles: dict[str, str] | None = None,
    ):
        self.missing_angles = missing_angles
        self.invalid_angles = invalid_angles or {}
        super().__init__(
            "Resource baseline is incomplete or invalid"
            + (
                "; missing angles: " + ", ".join(missing_angles)
                if missing_angles else ""
            )
            + (
                "; invalid angles: " + ", ".join(self.invalid_angles)
                if self.invalid_angles else ""
            )
        )


class BaselineApprovalValidationError(BookingBaselineSnapshotError):
    """Approval cannot proceed until all resource baseline angles are valid."""

    def __init__(self, missing_angles: list[str], invalid_angles: dict[str, str]):
        self.missing_angles = missing_angles
        self.invalid_angles = invalid_angles
        super().__init__("All six valid resource baseline angles are required for approval")


class SnapshotIntegrityError(BookingBaselineSnapshotError):
    pass


def _role_value(actor: User) -> str:
    return getattr(actor.role, "value", actor.role)


def _assert_snapshot_access(resource: Resource, actor: User) -> None:
    if _role_value(actor) != UserRole.ADMIN.value and resource.owner_id != actor.id:
        raise SnapshotAccessDeniedError(
            "Only the resource owner or an admin can create a booking baseline snapshot"
        )


def _find_snapshot(
    db: Session, booking_id: int
) -> BookingBaselineSnapshot | None:
    return db.scalar(
        select(BookingBaselineSnapshot).where(
            BookingBaselineSnapshot.booking_id == booking_id
        )
    )


def _validated_complete_snapshot(
    db: Session, snapshot: BookingBaselineSnapshot
) -> BookingBaselineSnapshot:
    images = list(
        db.scalars(
            select(BookingBaselineSnapshotImage).where(
                BookingBaselineSnapshotImage.snapshot_id == snapshot.id
            )
        ).all()
    )
    angles = [image.angle for image in images]
    if len(images) != len(REQUIRED_ANGLES) or set(angles) != set(REQUIRED_ANGLES):
        raise SnapshotIntegrityError(
            "Existing booking baseline snapshot is incomplete and will not be changed"
        )
    for image in images:
        if image.booking_id != snapshot.booking_id:
            raise SnapshotIntegrityError(
                "Booking baseline snapshot image is attached to the wrong booking"
            )
        if hashlib.sha256(bytes(image.image_data)).hexdigest() != image.sha256:
            raise SnapshotIntegrityError(
                f"Booking baseline snapshot image {image.id} failed SHA256 verification"
            )
    return snapshot


def get_booking_baseline_snapshot_images(
    db: Session,
    *,
    booking_id: int,
    actor: User,
) -> tuple[BookingBaselineSnapshot, list[BookingBaselineSnapshotImage]]:
    """Read the frozen images after checking booking access and every digest."""
    snapshot = get_booking_baseline_snapshot(db, booking_id=booking_id, actor=actor)
    images = list(db.scalars(
        select(BookingBaselineSnapshotImage)
        .where(BookingBaselineSnapshotImage.snapshot_id == snapshot.id)
        .order_by(BookingBaselineSnapshotImage.angle)
    ).all())
    return snapshot, images


def validate_resource_baseline(
    db: Session, *, resource_id: int
) -> dict[str, list | dict]:
    """Check six required rows, current SHA256 and decodable image quality.

    Quality warnings such as low resolution/exposure remain advisory as in the
    existing cv_engine contract; corrupt, unsupported, or mismatched content fails.
    """
    rows = list(
        db.scalars(
            select(ResourceBaselineImage).where(
                ResourceBaselineImage.resource_id == resource_id
            )
        ).all()
    )
    by_angle = {row.angle: row for row in rows}
    missing = [angle for angle in REQUIRED_ANGLES if angle not in by_angle]
    invalid: dict[str, str] = {}
    for angle, row in by_angle.items():
        if angle not in REQUIRED_ANGLES:
            invalid[angle] = "Unsupported baseline angle"
            continue
        data = bytes(row.image_data)
        if hashlib.sha256(data).hexdigest() != row.sha256:
            invalid[angle] = "SHA256 does not match stored image bytes"
            continue
        try:
            quality = assess_image_quality(data)
        except ImageValidationError as exc:
            invalid[angle] = str(exc)
            continue
        expected_mime = {
            "JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"
        }.get(quality.image_format)
        if expected_mime != row.mime_type or quality.file_size_bytes != row.byte_size:
            invalid[angle] = "Stored MIME type or byte size does not match image content"
    return {"missing_angles": missing, "invalid_angles": invalid}


def stage_booking_baseline_snapshot(
    db: Session, *, booking_id: int, actor: User
) -> BookingBaselineSnapshot:
    """Stage a complete immutable snapshot in the caller's transaction.

    Does not commit. The caller can atomically commit the snapshot with booking
    approval and its activity log, or roll back all three together.
    """
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise BookingNotFoundForSnapshotError("Booking not found")
    resource = db.get(Resource, booking.resource_id)
    if resource is None:
        raise BookingNotFoundForSnapshotError("Resource not found for booking")
    _assert_snapshot_access(resource, actor)
    existing = _find_snapshot(db, booking_id)
    if existing is not None:
        return _validated_complete_snapshot(db, existing)
    validation = validate_resource_baseline(db, resource_id=resource.id)
    if validation["missing_angles"] or validation["invalid_angles"]:
        raise IncompleteResourceBaselineError(
            validation["missing_angles"], validation["invalid_angles"]
        )
    baselines = list(
        db.scalars(
            select(ResourceBaselineImage).where(
                ResourceBaselineImage.resource_id == resource.id
            )
        ).all()
    )
    baselines_by_angle = {row.angle: row for row in baselines}
    snapshot = BookingBaselineSnapshot(
        booking_id=booking.id, resource_id=resource.id, created_by_id=actor.id
    )
    db.add(snapshot)
    db.flush()
    for angle in REQUIRED_ANGLES:
        baseline = baselines_by_angle[angle]
        db.add(
            BookingBaselineSnapshotImage(
                snapshot_id=snapshot.id,
                booking_id=booking.id,
                angle=angle,
                source_baseline_image_id=baseline.id,
                original_filename=baseline.original_filename,
                mime_type=baseline.mime_type,
                byte_size=baseline.byte_size,
                sha256=baseline.sha256,
                quality_metadata=dict(baseline.quality_metadata or {}),
                image_data=bytes(baseline.image_data),
            )
        )
    db.flush()
    return snapshot


def get_booking_baseline_snapshot(
    db: Session,
    *,
    booking_id: int,
    actor: User,
) -> BookingBaselineSnapshot:
    """Return a verified snapshot to the booking student, resource owner, or admin."""
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise BookingNotFoundForSnapshotError("Booking not found")
    resource = db.get(Resource, booking.resource_id)
    if resource is None:
        raise BookingNotFoundForSnapshotError("Resource not found for booking")
    is_admin = getattr(actor.role, "value", actor.role) == UserRole.ADMIN.value
    if not (is_admin or actor.id in (booking.student_id, resource.owner_id)):
        raise SnapshotAccessDeniedError(
            "You are not allowed to access this booking baseline snapshot"
        )
    snapshot = _find_snapshot(db, booking_id)
    if snapshot is None:
        raise LookupError("No immutable baseline snapshot is available for this booking")
    return _validated_complete_snapshot(db, snapshot)


def create_booking_baseline_snapshot(
    db: Session,
    *,
    booking_id: int,
    actor: User,
) -> BookingBaselineSnapshot:
    """Copy all six current resource baselines atomically for an approved booking.

    The function is deliberately not wired into booking approval. Shivansh can call
    it immediately after an approval succeeds, passing the approving owner/admin.
    A completed snapshot is returned unchanged on a safe retry.
    """

    booking = db.get(Booking, booking_id)
    if booking is None:
        raise BookingNotFoundForSnapshotError("Booking not found")
    resource = db.get(Resource, booking.resource_id)
    if resource is None:
        raise BookingNotFoundForSnapshotError("Resource not found for booking")
    _assert_snapshot_access(resource, actor)

    existing = _find_snapshot(db, booking_id)
    if existing is not None:
        return _validated_complete_snapshot(db, existing)

    status_value = getattr(booking.status, "value", booking.status)
    if status_value != BookingStatus.APPROVED.value:
        raise SnapshotRequiresApprovedBookingError(
            "Booking baseline snapshots can only be created while a booking is approved"
        )

    try:
        snapshot = stage_booking_baseline_snapshot(
            db, booking_id=booking_id, actor=actor
        )
        db.commit()
        db.refresh(snapshot)
    except IntegrityError as exc:
        db.rollback()
        # A concurrent caller may have completed the snapshot first. Returning a
        # verified complete snapshot makes the contract safe to retry.
        existing = _find_snapshot(db, booking_id)
        if existing is not None:
            return _validated_complete_snapshot(db, existing)
        raise exc
    except Exception:
        db.rollback()
        raise
    return snapshot
