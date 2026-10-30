
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.enums import UserRole
from app.models.resource import Resource
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.eligibility import (
    EligibilityRequirementCreate,
    EligibilityRequirementResponse,
)
from app.schemas.qualification import (
    QualificationCreate,
    QualificationResponse,
    QualificationReview,
)
from app.services.eligibility_service import (
    check_resource_eligibility,
    create_qualification,
    create_requirement,
    get_resource_requirements,
    get_user_qualifications,
    review_qualification,
)

router = APIRouter(tags=["Eligibility"])


@router.post(
    "/users/me/qualifications",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_qualification(
    qualification_data: QualificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.STUDENT)),
):
    qualification = create_qualification(
        db,
        current_user.id,
        qualification_data,
    )

    return APIResponse(
        success=True,
        message="Qualification submitted for verification",
        data=QualificationResponse.model_validate(qualification),
    )


@router.get(
    "/users/me/qualifications",
    response_model=APIResponse,
)
def list_my_qualifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    qualifications = get_user_qualifications(db, current_user.id)

    return APIResponse(
        success=True,
        message="Your qualifications retrieved successfully",
        data=[
            QualificationResponse.model_validate(item)
            for item in qualifications
        ],
    )


@router.patch(
    "/qualifications/{qualification_id}/verify",
    response_model=APIResponse,
)
def verify_qualification(
    qualification_id: int,
    review_data: QualificationReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    qualification = review_qualification(
        db,
        qualification_id,
        current_user.id,
        review_data,
    )

    if qualification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Qualification not found",
        )

    return APIResponse(
        success=True,
        message="Qualification review completed",
        data=QualificationResponse.model_validate(qualification),
    )


@router.post(
    "/resources/{resource_id}/eligibility-requirements",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_eligibility_requirement(
    resource_id: int,
    requirement_data: EligibilityRequirementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.OWNER, UserRole.ADMIN)
    ),
):
    resource = db.get(Resource, resource_id)

    if resource is None or not resource.is_active:
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
            detail="You are not allowed to manage this resource's requirements",
        )

    requirement = create_requirement(
        db,
        resource_id,
        requirement_data,
    )

    return APIResponse(
        success=True,
        message="Eligibility requirement added successfully",
        data=EligibilityRequirementResponse.model_validate(requirement),
    )


@router.get(
    "/resources/{resource_id}/eligibility-requirements",
    response_model=APIResponse,
)
def list_eligibility_requirements(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resource = db.get(Resource, resource_id)

    if resource is None or not resource.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    requirements = get_resource_requirements(db, resource_id)

    return APIResponse(
        success=True,
        message="Eligibility requirements retrieved successfully",
        data=[
            EligibilityRequirementResponse.model_validate(item)
            for item in requirements
        ],
    )


@router.get(
    "/resources/{resource_id}/eligibility",
    response_model=APIResponse,
)
def check_eligibility(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = check_resource_eligibility(
        db,
        current_user.id,
        resource_id,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    return APIResponse(
        success=True,
        message="Eligibility checked successfully",
        data=result,
    )