import hashlib
import ntpath
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.condition_report import ConditionReport
from app.models.condition_report_image import ConditionReportImage
from app.models.enums import BookingStatus, UserRole
from app.models.resource import Resource
from app.models.user import User
from cv_engine.angles import REQUIRED_ANGLES
from cv_engine.quality import (
    MAX_IMAGE_BYTES,
    ImageValidationError,
    assess_image_quality,
)


SUPPORTED_MIME_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class InvalidInspectionAngleError(ValueError):
    pass


class InvalidInspectionImageError(ValueError):
    pass


class UnsupportedInspectionImageTypeError(ValueError):
    pass


class InspectionImageTooLargeError(ValueError):
    pass


class DuplicateInspectionImageError(ValueError):
    pass


def _get_booking_report(
    db: Session,
    booking_id: int,
    report_id: int,
    actor: User | None = None,
) -> tuple[Booking, ConditionReport]:
    report = db.get(ConditionReport, report_id)
    if report is None or report.booking_id != booking_id:
        raise LookupError("Condition report not found for this booking")
    if report.report_type not in {"INITIAL", "FINAL"}:
        raise ValueError("Unsupported condition report stage")

    booking = db.get(Booking, booking_id)
    if booking is None:
        raise LookupError("Booking not found")
    resource = db.get(Resource, booking.resource_id)
    if resource is None:
        raise LookupError("Resource not found")

    if actor is not None:
        is_admin = actor.role == UserRole.ADMIN
        is_student = booking.student_id == actor.id
        is_owner = resource.owner_id == actor.id
        if not (is_admin or is_student or is_owner):
            raise PermissionError("You are not allowed to access these inspection images")
    return booking, report


def _validate_stage_state(booking: Booking, report: ConditionReport) -> None:
    status_value = getattr(booking.status, "value", booking.status)
    expected = (
        BookingStatus.APPROVED.value
        if report.report_type == "INITIAL"
        else BookingStatus.IN_USE.value
    )
    if status_value != expected:
        raise RuntimeError(
            f"{report.report_type.title()} inspection images require a {expected.lower()} booking"
        )


def _validate_upload(
    image_data: bytes,
    angle: str,
    declared_mime_type: str | None,
) -> tuple[str, int, str]:
    normalized_angle = angle.strip().upper() if isinstance(angle, str) else ""
    if normalized_angle not in REQUIRED_ANGLES:
        raise InvalidInspectionAngleError("Angle must be one of the six supported inspection angles")
    if len(image_data) > MAX_IMAGE_BYTES:
        raise InspectionImageTooLargeError("Image exceeds the 15 MiB size limit")
    try:
        quality = assess_image_quality(image_data)
    except ImageValidationError as exc:
        if len(image_data) > MAX_IMAGE_BYTES:
            raise InspectionImageTooLargeError("Image exceeds the 15 MiB size limit") from exc
        raise InvalidInspectionImageError(str(exc)) from exc

    actual_mime_type = SUPPORTED_MIME_TYPES.get(quality.image_format)
    if actual_mime_type is None:
        raise UnsupportedInspectionImageTypeError("Only JPEG, PNG, and WEBP images are supported")
    normalized_declared = (declared_mime_type or "").split(";", 1)[0].strip().lower()
    if normalized_declared != actual_mime_type:
        raise UnsupportedInspectionImageTypeError("Declared content type does not match the image content")
    return normalized_angle, quality.file_size_bytes, actual_mime_type


def _safe_original_filename(filename: str | None) -> str:
    name = ntpath.basename((filename or "inspection-image").replace("/", "\\"))
    name = name.replace("\x00", "").strip()
    return (name or "inspection-image")[:255]


def upload_condition_report_image(
    db: Session,
    *,
    booking_id: int,
    report_id: int,
    actor: User,
    angle: str,
    filename: str | None,
    declared_mime_type: str | None,
    image_data: bytes,
) -> tuple[Booking, ConditionReport, ConditionReportImage]:
    booking, report = _get_booking_report(db, booking_id, report_id, actor)
    _validate_stage_state(booking, report)
    normalized_angle, byte_size, mime_type = _validate_upload(
        image_data, angle, declared_mime_type
    )
    image = ConditionReportImage(
        report_id=report.id,
        angle=normalized_angle,
        original_filename=_safe_original_filename(filename),
        mime_type=mime_type,
        byte_size=byte_size,
        sha256=hashlib.sha256(image_data).hexdigest(),
        image_data=image_data,
        uploaded_by_id=actor.id,
    )
    db.add(image)
    try:
        db.commit()
        db.refresh(image)
    except IntegrityError as exc:
        db.rollback()
        detail = str(getattr(exc, "orig", exc))
        if (
            "uq_condition_report_images_report_angle" not in detail
            and "condition_report_images.report_id, condition_report_images.angle" not in detail
        ):
            raise
        raise DuplicateInspectionImageError(
            "An image for this angle already exists in this condition report"
        ) from exc
    return booking, report, image


def list_condition_report_images(
    db: Session,
    *,
    booking_id: int,
    report_id: int,
    actor: User,
) -> tuple[Booking, ConditionReport, list[ConditionReportImage]]:
    booking, report = _get_booking_report(db, booking_id, report_id, actor)
    images = list(
        db.scalars(
            select(ConditionReportImage)
            .where(ConditionReportImage.report_id == report_id)
            .order_by(ConditionReportImage.angle.asc())
        ).all()
    )
    return booking, report, images


def get_condition_report_image(
    db: Session,
    *,
    booking_id: int,
    report_id: int,
    image_id: int,
    actor: User,
) -> tuple[ConditionReport, ConditionReportImage]:
    _, report = _get_booking_report(db, booking_id, report_id, actor)
    image = db.get(ConditionReportImage, image_id)
    if image is None or image.report_id != report_id:
        raise LookupError("Inspection image not found")
    return report, image


def load_booking_inspection_images(
    db: Session,
    booking_id: int,
    initial_report_id: int,
    final_report_id: int,
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """Load explicitly selected INITIAL and FINAL CV inputs, omitting absent angles."""
    if db.get(Booking, booking_id) is None:
        raise LookupError("Booking not found")

    selected_reports = (
        (initial_report_id, "INITIAL"),
        (final_report_id, "FINAL"),
    )
    result: list[dict[str, bytes]] = []
    for report_id, expected_stage in selected_reports:
        report = db.get(ConditionReport, report_id)
        if report is None or report.booking_id != booking_id:
            raise LookupError(
                f"{expected_stage} condition report {report_id} was not found for booking {booking_id}"
            )
        if report.report_type != expected_stage:
            raise ValueError(
                f"Condition report {report_id} has type {report.report_type!r}; expected {expected_stage}"
            )
        images: Iterable[ConditionReportImage] = db.scalars(
            select(ConditionReportImage).where(
                ConditionReportImage.report_id == report.id
            )
        ).all()
        result.append({image.angle: bytes(image.image_data) for image in images})
    return result[0], result[1]
