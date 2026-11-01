
from io import BytesIO
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.enums import UserRole
from app.models.resource import Resource
from app.models.resource_image import ResourceImage
from app.models.resource_baseline_image import ResourceBaselineImage
from app.models.user import User
from app.schemas.resource import (
    ResourceCreate,
    ResourceResponse,
    ResourceUpdate,
)
from app.services.resource_service import (
    create_resource,
    get_owner_resources,
    get_resource,
    get_resources,
    update_resource,
)
from app.services.resource_baseline_service import (
    BaselineAccessDeniedError,
    BaselineImageNotFoundError,
    BaselineImageTooLargeError,
    BaselineResourceNotFoundError,
    DuplicateBaselineAngleError,
    InvalidBaselineAngleError,
    InvalidBaselineImageError,
    UnsupportedBaselineImageTypeError,
    create_resource_baseline_image,
    list_resource_baseline_images,
    replace_resource_baseline_image,
)
from app.services.booking_baseline_snapshot_service import (
    validate_resource_baseline,
)
from cv_engine.quality import MAX_IMAGE_BYTES
from cv_engine.angles import REQUIRED_ANGLES

router = APIRouter(prefix="/resources", tags=["Resources"])

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000

ALLOWED_IMAGE_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def validate_resource_image(
    image_bytes: bytes,
    declared_content_type: str | None,
) -> str:
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image file is empty",
        )

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image must not exceed 15 MB",
        )

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            detected_format = image.format
            width, height = image.size

            if detected_format not in ALLOWED_IMAGE_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail="Only JPEG, PNG and WEBP images are supported",
                )

            if width * height > MAX_IMAGE_PIXELS:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Image dimensions must not exceed 40 megapixels",
                )

            image.verify()

        expected_content_type = ALLOWED_IMAGE_TYPES[detected_format]

    except HTTPException:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or corrupted image",
        ) from exc

    if declared_content_type != expected_content_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Image content type does not match the actual image format",
        )

    return expected_content_type


@router.get("", response_model=list[ResourceResponse])
def list_resources(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_resources(db, skip=skip, limit=limit)


@router.post(
    "",
    response_model=ResourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_resource_endpoint(
    resource_data: ResourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.OWNER, UserRole.ADMIN)
    ),
):
    return create_resource(
        db=db,
        owner_id=current_user.id,
        resource_data=resource_data,
    )


@router.get("/owner", response_model=list[ResourceResponse])
def list_owner_resources(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.OWNER, UserRole.ADMIN)
    ),
):
    return get_owner_resources(db, current_user)


@router.post(
    "/{resource_id}/images",
    status_code=status.HTTP_201_CREATED,
)
async def upload_resource_image(
    resource_id: int,
    file: UploadFile = File(...),
    is_primary: bool | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.OWNER, UserRole.ADMIN)
    ),
):
    try:
        resource = db.scalar(
            select(Resource)
            .where(Resource.id == resource_id)
            .with_for_update()
        )

        if resource is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found",
            )

        if (
            current_user.role != UserRole.ADMIN
            and resource.owner_id != current_user.id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not allowed to upload images for this resource",
            )

        image_bytes = await file.read(MAX_IMAGE_BYTES + 1)

        mime_type = validate_resource_image(
            image_bytes,
            file.content_type,
        )

        existing_primary = db.scalar(
            select(ResourceImage.id).where(
                ResourceImage.resource_id == resource_id,
                ResourceImage.is_primary.is_(True),
            )
        )

        make_primary = (
            is_primary is True
            or existing_primary is None
        )

        if make_primary:
            db.query(ResourceImage).filter(
                ResourceImage.resource_id == resource_id,
                ResourceImage.is_primary.is_(True),
            ).update(
                {ResourceImage.is_primary: False},
                synchronize_session="fetch",
            )

        filename = Path(file.filename or "resource-image").name[:255]

        resource_image = ResourceImage(
            resource_id=resource_id,
            original_filename=filename,
            mime_type=mime_type,
            byte_size=len(image_bytes),
            image_data=image_bytes,
            is_primary=make_primary,
            uploaded_by_id=current_user.id,
        )

        db.add(resource_image)
        db.commit()
        db.refresh(resource_image)

        return {
            "id": resource_image.id,
            "resource_id": resource_id,
            "url": resource_image.url,
            "is_primary": resource_image.is_primary,
        }

    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not save image. Please retry.",
        ) from exc
    except Exception:
        db.rollback()
        raise
    finally:
        await file.close()


@router.get("/{resource_id}/images/{image_id}")
def get_resource_image(
    resource_id: int,
    image_id: int,
    db: Session = Depends(get_db),
):
    image = db.scalar(
        select(ResourceImage)
        .join(Resource, Resource.id == ResourceImage.resource_id)
        .where(
            ResourceImage.id == image_id,
            ResourceImage.resource_id == resource_id,
            Resource.is_active.is_(True),
        )
    )

    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource image not found",
        )

    return Response(
        content=image.image_data,
        media_type=image.mime_type,
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Length": str(image.byte_size),
            "X-Content-Type-Options": "nosniff",
        },
    )


def _baseline_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BaselineResourceNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, BaselineAccessDeniedError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, (DuplicateBaselineAngleError, BaselineImageNotFoundError)):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, BaselineImageTooLargeError):
        code = status.HTTP_413_CONTENT_TOO_LARGE
    elif isinstance(exc, UnsupportedBaselineImageTypeError):
        code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    elif isinstance(exc, (InvalidBaselineAngleError, InvalidBaselineImageError)):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        raise exc
    return HTTPException(status_code=code, detail=str(exc))


def _baseline_metadata(image: ResourceBaselineImage) -> dict:
    return {
        "id": image.id,
        "resource_id": image.resource_id,
        "angle": image.angle,
        "original_filename": image.original_filename,
        "mime_type": image.mime_type,
        "byte_size": image.byte_size,
        "sha256": image.sha256,
        "uploaded_at": image.uploaded_at,
        "updated_at": image.updated_at,
    }


@router.post("/{resource_id}/baseline-images", status_code=status.HTTP_201_CREATED)
async def upload_resource_baseline_image(
    resource_id: int,
    file: UploadFile = File(...),
    angle: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
):
    try:
        image_data = await file.read(MAX_IMAGE_BYTES + 1)
        if len(image_data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image exceeds the 15 MiB size limit")
        image = create_resource_baseline_image(
            db, resource_id=resource_id, actor=current_user, angle=angle,
            filename=file.filename, declared_mime_type=file.content_type,
            image_data=image_data,
        )
        return _baseline_metadata(image)
    except HTTPException:
        raise
    except (LookupError, PermissionError, ValueError) as exc:
        raise _baseline_http_error(exc) from exc
    finally:
        await file.close()


@router.put("/{resource_id}/baseline-images/{angle}")
async def replace_resource_baseline_image_endpoint(
    resource_id: int,
    angle: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
):
    try:
        image_data = await file.read(MAX_IMAGE_BYTES + 1)
        if len(image_data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image exceeds the 15 MiB size limit")
        image = replace_resource_baseline_image(
            db, resource_id=resource_id, actor=current_user, angle=angle,
            filename=file.filename, declared_mime_type=file.content_type,
            image_data=image_data,
        )
        return _baseline_metadata(image)
    except HTTPException:
        raise
    except (LookupError, PermissionError, ValueError) as exc:
        raise _baseline_http_error(exc) from exc
    finally:
        await file.close()


@router.get("/{resource_id}/baseline-images")
def get_resource_baseline_images(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
):
    try:
        images = list_resource_baseline_images(db, resource_id=resource_id, actor=current_user)
        validation = validate_resource_baseline(db, resource_id=resource_id)
        invalid_angles = validation["invalid_angles"]
        response_images = []
        for image in images:
            metadata = _baseline_metadata(image)
            metadata["validation_status"] = (
                "invalid" if image.angle in invalid_angles else "valid"
            )
            metadata["validation_error"] = invalid_angles.get(image.angle)
            response_images.append(metadata)
        return {
            "required_angles": list(REQUIRED_ANGLES),
            "missing_angles": validation["missing_angles"],
            "invalid_angles": invalid_angles,
            "images": response_images,
        }
    except (LookupError, PermissionError, ValueError) as exc:
        raise _baseline_http_error(exc) from exc


@router.get("/{resource_id}", response_model=ResourceResponse)
def get_resource_endpoint(
    resource_id: int,
    db: Session = Depends(get_db),
):
    resource = get_resource(db, resource_id)

    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    return resource


@router.patch("/{resource_id}", response_model=ResourceResponse)
def update_resource_endpoint(
    resource_id: int,
    update_data: ResourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.OWNER, UserRole.ADMIN)
    ),
):
    resource = db.get(Resource, resource_id)

    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    if (
        current_user.role != UserRole.ADMIN
        and resource.owner_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to update this resource",
        )

    try:
        return update_resource(db, resource, update_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
