from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
    AliasChoices,
)

from app.models.enums import BookingStatus


class BookingCreate(BaseModel):
    resource_id: int = Field(gt=0)
    start_at: datetime
    end_at: datetime
    purpose: str = Field(min_length=5, max_length=2000)

    @model_validator(mode="after")
    def validate_booking_time(self):
        try:
            if self.end_at <= self.start_at:
                raise ValueError(
                    "Booking end time must be after start time"
                )
        except TypeError as exc:
            raise ValueError(
                "Booking dates must use compatible timezones"
            ) from exc

        return self


class BookingDecision(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str | None = Field(default=None, max_length=2000)


class BookingResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    id: int
    user_id: int = Field(
        validation_alias=AliasChoices("student_id", "user_id")
    )
    resource_id: int
    start_at: datetime
    end_at: datetime
    purpose: str
    status: BookingStatus
    approved_by_id: int | None
    approved_at: datetime | None
    reason: str | None = Field(
        validation_alias=AliasChoices("decision_note", "reason")
    )
    checkin_at: datetime | None
    checkout_at: datetime | None
    created_at: datetime


class ConditionReportCreate(BaseModel):
    condition_description: str = Field(min_length=5, max_length=5000)
    evidence_reference: str | None = Field(default=None, max_length=500)


class ConditionReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    submitted_by_id: int
    report_type: str
    condition_description: str
    evidence_reference: str | None
    created_at: datetime
