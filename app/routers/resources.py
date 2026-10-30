
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.enums import UserRole
from app.models.resource import Resource
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
