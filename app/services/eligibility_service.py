
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.eligibility_requirement import EligibilityRequirement
from app.models.enums import QualificationStatus
from app.models.resource import Resource
from app.models.user_qualification import UserQualification
from app.schemas.eligibility import (
    EligibilityCheckItem,
    EligibilityCheckResponse,
    EligibilityRequirementCreate,
)
from app.schemas.qualification import QualificationCreate, QualificationReview


def normalize_value(value: str) -> str:
    """Normalize text for case-insensitive, whitespace-trimmed matching."""
    return value.strip().casefold()


def create_qualification(
    db: Session,
    user_id: int,
    qualification_data: QualificationCreate,
) -> UserQualification:
    qualification = UserQualification(
        user_id=user_id,
        qualification_type=qualification_data.qualification_type.strip(),
        qualification_title=qualification_data.qualification_title.strip(),
        description=qualification_data.description,
        evidence_reference=qualification_data.evidence_reference,
        status=QualificationStatus.PENDING,
    )

    db.add(qualification)
    db.commit()
    db.refresh(qualification)
    return qualification


def get_user_qualifications(
    db: Session,
    user_id: int,
) -> list[UserQualification]:
    statement = (
        select(UserQualification)
        .where(UserQualification.user_id == user_id)
        .order_by(UserQualification.created_at.desc())
    )
    return list(db.scalars(statement).all())


def review_qualification(
    db: Session,
    qualification_id: int,
    admin_id: int,
    review_data: QualificationReview,
) -> UserQualification | None:
    qualification = db.get(UserQualification, qualification_id)

    if qualification is None:
        return None

    qualification.status = review_data.status
    qualification.reviewed_by_id = admin_id
    qualification.reviewed_at = datetime.now(timezone.utc)
    qualification.review_note = (
        review_data.review_note.strip()
        if review_data.review_note
        else None
    )

    db.commit()
    db.refresh(qualification)
    return qualification


def create_requirement(
    db: Session,
    resource_id: int,
    requirement_data: EligibilityRequirementCreate,
) -> EligibilityRequirement:
    requirement = EligibilityRequirement(
        resource_id=resource_id,
        requirement_type=requirement_data.requirement_type.strip(),
        requirement_value=requirement_data.requirement_value.strip(),
        is_mandatory=requirement_data.is_mandatory,
    )

    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


def get_resource_requirements(
    db: Session,
    resource_id: int,
) -> list[EligibilityRequirement]:
    statement = (
        select(EligibilityRequirement)
        .where(EligibilityRequirement.resource_id == resource_id)
        .order_by(EligibilityRequirement.id.asc())
    )
    return list(db.scalars(statement).all())


def check_resource_eligibility(
    db: Session,
    user_id: int,
    resource_id: int,
) -> EligibilityCheckResponse | None:
    resource = db.get(Resource, resource_id)

    if resource is None or not resource.is_active:
        return None

    requirements = get_resource_requirements(db, resource_id)

    verified_statement = select(UserQualification).where(
        UserQualification.user_id == user_id,
        UserQualification.status == QualificationStatus.VERIFIED,
    )
    verified_qualifications = db.scalars(verified_statement).all()

    verified_pairs = {
        (
            normalize_value(qualification.qualification_type),
            normalize_value(qualification.qualification_title),
        )
        for qualification in verified_qualifications
    }

    requirement_results = []

    for requirement in requirements:
        matched = (
            normalize_value(requirement.requirement_type),
            normalize_value(requirement.requirement_value),
        ) in verified_pairs

        requirement_results.append(
            EligibilityCheckItem(
                requirement_type=requirement.requirement_type,
                requirement_value=requirement.requirement_value,
                is_mandatory=requirement.is_mandatory,
                satisfied=matched,
            )
        )

    eligible = all(
        item.satisfied
        for item in requirement_results
        if item.is_mandatory
    )

    return EligibilityCheckResponse(
        resource_id=resource_id,
        eligible=eligible,
        requirements=requirement_results,
    )