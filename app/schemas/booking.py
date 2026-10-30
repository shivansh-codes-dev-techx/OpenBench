from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import BookingStatus


class BookingCreate(BaseModel):
    resource_id: int = Field(gt=0)
    start_at: datetime
    end_at: datetime
    purpose: str = Field(min_length=5, max_length=2000)

    @model_validator(mode="after")
    def validate_booking_time(self):
        if self.end_at <= self.start_at:
            raise ValueError("Booking end time must be after start time")
        return self


class BookingDecision(BaseModel):
    decision_note: str | None = None


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    resource_id: int
    start_at: datetime
    end_at: datetime
    purpose: str
    status: BookingStatus
    approved_by_id: int | None
    approved_at: datetime | None
    decision_note: str | None
    checkin_at: datetime | None
    checkout_at: datetime | None
    created_at: datetime