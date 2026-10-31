import pytest

from pydantic import ValidationError

from app.schemas.user import UserRegister
from app.schemas.booking import BookingCreate
from app.schemas.resource import ResourceCreate
from app.schemas.qualification import QualificationReview

from app.models.enums import (
    UserRole,
    ResourceType,
    QualificationStatus,
)


def test_valid_user_registration():
    user = UserRegister(
        full_name="Test Student",
        email="student@example.com",
        password="password123",
    )
    assert user.role == UserRole.STUDENT


def test_admin_registration_rejected():
    with pytest.raises(ValidationError):
        UserRegister(
            full_name="Admin User",
            email="admin@example.com",
            password="password123",
            role=UserRole.ADMIN,
        )


def test_invalid_email_rejected():
    with pytest.raises(ValidationError):
        UserRegister(
            full_name="Test Student",
            email="invalid-email",
            password="password123",
        )


def test_invalid_booking_time_rejected():
    with pytest.raises(ValidationError):
        BookingCreate(
            resource_id=1,
            start_at="2026-10-31T15:00:00",
            end_at="2026-10-31T14:00:00",
            purpose="Laboratory research",
        )


def test_valid_booking():
    booking = BookingCreate(
        resource_id=1,
        start_at="2026-10-31T14:00:00",
        end_at="2026-10-31T15:00:00",
        purpose="Laboratory research",
    )
    assert booking.resource_id == 1


def test_invalid_resource_availability():
    with pytest.raises(ValidationError):
        ResourceCreate(
            title="Science Lab",
            category="Laboratory",
            resource_type=ResourceType.SPACE,
            location="Block A",
            available_from="2026-10-31T15:00:00",
            available_until="2026-10-31T14:00:00",
        )


def test_pending_qualification_review_rejected():
    with pytest.raises(ValidationError):
        QualificationReview(status=QualificationStatus.PENDING)


def test_verified_qualification_review():
    review = QualificationReview(status=QualificationStatus.VERIFIED)
    assert review.status == QualificationStatus.VERIFIED