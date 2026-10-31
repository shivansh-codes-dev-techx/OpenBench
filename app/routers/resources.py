
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
from app.models.user import User
from app.schemas.resource import (
    ResourceCreate,
    ResourceResponse,
    ResourceUpdate,
)
from app.services.resource_service import (
    create_resource,
    get_resource,
    get_resources,
    update_resource,
)

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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc