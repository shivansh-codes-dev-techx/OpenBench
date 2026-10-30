from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import QualificationStatus


class QualificationCreate(BaseModel):
    qualification_type: str = Field(min_length=2, max_length=100)
    qualification_title: str = Field(min_length=2, max_length=150)
    description: str | None = None
    evidence_reference: str | None = Field(
        default=None, max_length=500
    )


class QualificationReview(BaseModel):
    status: QualificationStatus
    review_note: str | None = None

    @field_validator("status")
    @classmethod
    def validate_review_status(cls, value):
        if value == QualificationStatus.PENDING:
            raise ValueError("Review status must be VERIFIED or REJECTED")
        return value


class QualificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    qualification_type: str
    qualification_title: str
    description: str | None
    evidence_reference: str | None
    status: QualificationStatus
    reviewed_by_id: int | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime