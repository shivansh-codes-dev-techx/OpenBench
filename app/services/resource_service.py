
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.resource import Resource
from app.schemas.resource import ResourceCreate, ResourceUpdate


def validate_availability(start, end):
    if start is None or end is None:
        return

    try:
        if end <= start:
            raise ValueError("Availability end must be after start")
    except TypeError as exc:
        raise ValueError(
            "Availability dates must use compatible timezones"
        ) from exc


def create_resource(
    db: Session,
    owner_id: int,
    resource_data: ResourceCreate,
) -> Resource:
    validate_availability(
        resource_data.available_from,
        resource_data.available_until,
    )

    resource = Resource(
        owner_id=owner_id,
        **resource_data.model_dump(),
    )

    db.add(resource)
    db.commit()
    db.refresh(resource)

    return resource


def get_resources(
    db: Session,
    skip: int = 0,
    limit: int = 20,
) -> list[Resource]:
    statement = (
        select(Resource)
        .where(Resource.is_active.is_(True))
        .order_by(Resource.created_at.desc(), Resource.id.desc())
        .offset(skip)
        .limit(limit)
    )

    return list(db.scalars(statement).all())


def get_resource(
    db: Session,
    resource_id: int,
) -> Resource | None:
    statement = select(Resource).where(
        Resource.id == resource_id,
        Resource.is_active.is_(True),
    )

    return db.scalar(statement)


def update_resource(
    db: Session,
    resource: Resource,
    update_data: ResourceUpdate,
) -> Resource:
    changes = update_data.model_dump(exclude_unset=True)

    if not changes:
        raise ValueError("At least one field must be provided")

    new_start = changes.get(
        "available_from",
        resource.available_from,
    )
    new_end = changes.get(
        "available_until",
        resource.available_until,
    )

    validate_availability(new_start, new_end)

    for field, value in changes.items():
        setattr(resource, field, value)

    db.commit()
    db.refresh(resource)

    return resource
