"""Owner/admin-managed six-angle resource baseline storage."""

import hashlib
import ntpath

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.resource import Resource
from app.models.resource_baseline_image import ResourceBaselineImage
from app.models.user import User
from cv_engine.angles import REQUIRED_ANGLES
from cv_engine.quality import MAX_IMAGE_BYTES, ImageValidationError, assess_image_quality


SUPPORTED_MIME_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class ResourceBaselineError(ValueError):
    """Base error for the resource-baseline service contract."""


class InvalidBaselineAngleError(ResourceBaselineError):
    pass


class InvalidBaselineImageError(ResourceBaselineError):
    pass


class UnsupportedBaselineImageTypeError(ResourceBaselineError):
    pass


class BaselineImageTooLargeError(ResourceBaselineError):
    pass


class DuplicateBaselineAngleError(ResourceBaselineError):
    pass


class BaselineImageNotFoundError(LookupError):
    pass


class BaselineResourceNotFoundError(LookupError):
    pass


class BaselineAccessDeniedError(PermissionError):
    pass


def _role_value(actor: User) -> str:
    return getattr(actor.role, "value", actor.role)


def _get_managed_resource(db: Session, resource_id: int, actor: User) -> Resource:
    resource = db.scalar(
        select(Resource)
        .where(Resource.id == resource_id)
        .with_for_update()
    )
    if resource is None:
        raise BaselineResourceNotFoundError("Resource not found")
    if _role_value(actor) != UserRole.ADMIN.value and resource.owner_id != actor.id:
        raise BaselineAccessDeniedError(
            "Only the resource owner or an admin can manage baseline images"
        )
    return resource


def _validate_upload(
    image_data: bytes,
    angle: str,
    declared_mime_type: str | None,
) -> tuple[str, int, str]:
    normalized_angle = angle.strip().upper() if isinstance(angle, str) else ""
    if normalized_angle not in REQUIRED_ANGLES:
        raise InvalidBaselineAngleError(
            "Angle must be one of FRONT, BACK, LEFT, RIGHT, TOP, or BOTTOM"
        )
    if not isinstance(image_data, bytes) or not image_data:
        raise InvalidBaselineImageError("Image data is empty or invalid")
    if len(image_data) > MAX_IMAGE_BYTES:
        raise BaselineImageTooLargeError("Image exceeds the 15 MiB size limit")

    try:
        quality = assess_image_quality(image_data)
    except ImageValidationError as exc:
        if len(image_data) > MAX_IMAGE_BYTES:
            raise BaselineImageTooLargeError("Image exceeds the 15 MiB size limit") from exc
        raise InvalidBaselineImageError(str(exc)) from exc

    mime_type = SUPPORTED_MIME_TYPES.get(quality.image_format)
    if mime_type is None:
        raise UnsupportedBaselineImageTypeError(
            "Only JPEG, PNG, and WEBP images are supported"
        )
    normalized_declared = (declared_mime_type or "").split(";", 1)[0].strip().lower()
    if normalized_declared != mime_type:
        raise UnsupportedBaselineImageTypeError(
            "Declared content type does not match the image content"
        )
    return normalized_angle, quality, mime_type


def _safe_original_filename(filename: str | None) -> str:
    name = ntpath.basename((filename or "baseline-image").replace("/", "\\"))
    name = name.replace("\x00", "").strip()
    return (name or "baseline-image")[:255]


def create_resource_baseline_image(
    db: Session,
    *,
    resource_id: int,
    actor: User,
    angle: str,
    filename: str | None,
    declared_mime_type: str | None,
    image_data: bytes,
) -> ResourceBaselineImage:
    """Create one baseline angle; callers must use replace for an existing angle."""

    _get_managed_resource(db, resource_id, actor)
    normalized_angle, quality, mime_type = _validate_upload(
        image_data, angle, declared_mime_type
    )
    existing = db.scalar(
        select(ResourceBaselineImage.id).where(
            ResourceBaselineImage.resource_id == resource_id,
            ResourceBaselineImage.angle == normalized_angle,
        )
    )
    if existing is not None:
        raise DuplicateBaselineAngleError(
            "A baseline image for this resource angle already exists; use replacement"
        )

    baseline = ResourceBaselineImage(
        resource_id=resource_id,
        angle=normalized_angle,
        original_filename=_safe_original_filename(filename),
        mime_type=mime_type,
        byte_size=quality.file_size_bytes,
        sha256=hashlib.sha256(image_data).hexdigest(),
        quality_metadata=quality.to_dict(),
        image_data=image_data,
        uploaded_by_id=actor.id,
    )
    db.add(baseline)
    try:
        db.commit()
        db.refresh(baseline)
    except IntegrityError as exc:
        db.rollback()
        detail = str(getattr(exc, "orig", exc))
        if (
            "uq_resource_baseline_images_resource_angle" in detail
            or "resource_baseline_images.resource_id, resource_baseline_images.angle"
            in detail
        ):
            raise DuplicateBaselineAngleError(
                "A baseline image for this resource angle already exists; use replacement"
            ) from exc
        raise
    except Exception:
        db.rollback()
        raise
    return baseline


def replace_resource_baseline_image(
    db: Session,
    *,
    resource_id: int,
    actor: User,
    angle: str,
    filename: str | None,
    declared_mime_type: str | None,
    image_data: bytes,
) -> ResourceBaselineImage:
    """Explicitly replace one existing baseline image in a single DB transaction."""

    _get_managed_resource(db, resource_id, actor)
    normalized_angle, quality, mime_type = _validate_upload(
        image_data, angle, declared_mime_type
    )
    baseline = db.scalar(
        select(ResourceBaselineImage).where(
            ResourceBaselineImage.resource_id == resource_id,
            ResourceBaselineImage.angle == normalized_angle,
        )
    )
    if baseline is None:
        raise BaselineImageNotFoundError(
            "No baseline image exists for this resource angle; create it first"
        )

    baseline.original_filename = _safe_original_filename(filename)
    baseline.mime_type = mime_type
    baseline.byte_size = quality.file_size_bytes
    baseline.sha256 = hashlib.sha256(image_data).hexdigest()
    baseline.quality_metadata = quality.to_dict()
    baseline.image_data = image_data
    baseline.uploaded_by_id = actor.id
    try:
        db.commit()
        db.refresh(baseline)
    except Exception:
        db.rollback()
        raise
    return baseline


def list_resource_baseline_images(
    db: Session,
    *,
    resource_id: int,
    actor: User,
) -> list[ResourceBaselineImage]:
    """List baselines for management after enforcing the owner/admin contract."""

    _get_managed_resource(db, resource_id, actor)
    return list(
        db.scalars(
            select(ResourceBaselineImage)
            .where(ResourceBaselineImage.resource_id == resource_id)
            .order_by(ResourceBaselineImage.angle.asc())
        ).all()
    )
