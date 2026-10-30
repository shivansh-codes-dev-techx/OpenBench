
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.activity_log import ActivityLog
from app.models.booking import Booking
from app.models.eligibility_requirement import EligibilityRequirement
from app.models.enums import BookingStatus, UserRole
from app.models.resource import Resource
from app.models.user import User
from app.core.security import hash_password, create_access_token
from app.models.condition_report import ConditionReport

@pytest.fixture
def test_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client, TestingSession

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def register_user(client, name, email, role):
    response = client.post(
        "/auth/register",
        json={
            "full_name": name,
            "email": email,
            "password": "StrongPass123",
            "role": role,
        },
    )

    assert response.status_code == 201

    token = response.json()["data"]["access_token"]

    return {"Authorization": f"Bearer {token}"}


def create_admin(TestingSession):
    db = TestingSession()

    try:
        admin = User(
            full_name="Test Admin",
            email="admin-booking@example.com",
            hashed_password=hash_password("StrongPass123"),
            role=UserRole.ADMIN,
            is_active=True,
        )

        db.add(admin)
        db.commit()
        db.refresh(admin)

        token = create_access_token(admin.id)

        return {"Authorization": f"Bearer {token}"}

    finally:
        db.close()


def create_resource(client, owner_headers, title="Projector", **extra):
    payload = {
        "title": title,
        "description": "Campus projector",
        "category": "Electronics",
        "resource_type": "EQUIPMENT",
        "location": "Block A",
        "usage_rules": "Handle with care",
        **extra,
    }

    response = client.post(
        "/resources",
        json=payload,
        headers=owner_headers,
    )

    assert response.status_code == 201

    return response.json()


def booking_payload(resource_id, **extra):
    start = datetime.now(timezone.utc) + timedelta(days=2)
    end = start + timedelta(hours=2)

    return {
        "resource_id": resource_id,
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "purpose": "Academic project work",
        **extra,
    }


def test_student_creates_pending_booking_and_activity_log(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Student One", "student1@example.com", "STUDENT"
    )

    owner = register_user(
        client, "Owner One", "owner1@example.com", "OWNER"
    )

    resource = create_resource(client, owner)

    response = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["user_id"] > 0
    assert data["status"] == "PENDING"
    assert "student_id" not in data
    assert "decision_note" not in data

    db = TestingSession()

    try:
        booking = db.get(Booking, data["id"])

        assert booking is not None
        assert booking.status == BookingStatus.PENDING

        log = db.scalar(
            select(ActivityLog).where(
                ActivityLog.entity_type == "BOOKING",
                ActivityLog.entity_id == booking.id,
                ActivityLog.action == "BOOKING_CREATED",
            )
        )

        assert log is not None
        assert log.actor_id == booking.student_id

    finally:
        db.close()


def test_client_cannot_spoof_booking_student_id(test_context):
    client, _ = test_context

    student = register_user(
        client, "Student Two", "student2@example.com", "STUDENT"
    )

    owner = register_user(
        client, "Owner Two", "owner2@example.com", "OWNER"
    )

    resource = create_resource(client, owner)

    response = client.post(
        "/bookings",
        json=booking_payload(
            resource["id"],
            user_id=999999,
            student_id=999999,
        ),
        headers=student,
    )

    assert response.status_code == 201
    assert response.json()["data"]["user_id"] != 999999


def test_missing_resource_returns_404(test_context):
    client, _ = test_context

    student = register_user(
        client, "Student Four", "student4@example.com", "STUDENT"
    )

    response = client.post(
        "/bookings",
        json=booking_payload(999999),
        headers=student,
    )

    assert response.status_code == 404


def test_inactive_resource_rejects_booking(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Student Five", "student5@example.com", "STUDENT"
    )

    owner = register_user(
        client, "Owner Three", "owner3@example.com", "OWNER"
    )

    resource_data = create_resource(client, owner)

    db = TestingSession()

    try:
        resource = db.get(Resource, resource_data["id"])
        resource.is_active = False
        db.commit()

    finally:
        db.close()

    response = client.post(
        "/bookings",
        json=booking_payload(resource_data["id"]),
        headers=student,
    )

    assert response.status_code == 409


def test_booking_must_fit_resource_availability_window(test_context):
    client, _ = test_context

    student = register_user(
        client, "Student Six", "student6@example.com", "STUDENT"
    )

    owner = register_user(
        client, "Owner Four", "owner4@example.com", "OWNER"
    )

    available_from = datetime.now(timezone.utc) + timedelta(days=3)
    available_until = available_from + timedelta(days=2)

    resource = create_resource(
        client,
        owner,
        available_from=available_from.isoformat(),
        available_until=available_until.isoformat(),
    )

    too_early = {
        "resource_id": resource["id"],
        "start_at": (
            available_from - timedelta(hours=2)
        ).isoformat(),
        "end_at": (
            available_from + timedelta(hours=1)
        ).isoformat(),
        "purpose": "Academic project work",
    }

    response = client.post(
        "/bookings",
        json=too_early,
        headers=student,
    )

    assert response.status_code == 409


def test_ineligible_student_cannot_create_booking(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Student Seven", "student7@example.com", "STUDENT"
    )

    owner = register_user(
        client, "Owner Five", "owner5@example.com", "OWNER"
    )

    resource = create_resource(client, owner)

    db = TestingSession()

    try:
        db.add(
            EligibilityRequirement(
                resource_id=resource["id"],
                requirement_type="CERTIFICATION",
                requirement_value="SAFETY",
                is_mandatory=True,
            )
        )

        db.commit()

    finally:
        db.close()

    response = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )

    assert response.status_code == 403


def test_student_sees_only_own_bookings(test_context):
    client, _ = test_context

    student_one = register_user(
        client, "Student Eight", "student8@example.com", "STUDENT"
    )

    student_two = register_user(
        client, "Student Nine", "student9@example.com", "STUDENT"
    )

    owner = register_user(
        client, "Owner Six", "owner6@example.com", "OWNER"
    )

    resource = create_resource(client, owner)

    first = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student_one,
    )

    second = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student_two,
    )

    assert first.status_code == 201
    assert second.status_code == 201

    response = client.get(
        "/bookings/me",
        headers=student_one,
    )

    assert response.status_code == 200

    bookings = response.json()["data"]

    assert len(bookings) == 1
    assert bookings[0]["id"] == first.json()["data"]["id"]


def test_owner_cannot_create_or_list_student_bookings(test_context):
    client, _ = test_context

    headers = register_user(
        client,
        "Owner User",
        "owner-booking@example.com",
        "OWNER",
    )

    create_response = client.post(
        "/bookings",
        json=booking_payload(1),
        headers=headers,
    )

    list_response = client.get(
        "/bookings/me",
        headers=headers,
    )

    assert create_response.status_code == 403
    assert list_response.status_code == 403


def test_admin_cannot_create_or_list_student_bookings(test_context):
    client, TestingSession = test_context

    headers = create_admin(TestingSession)

    create_response = client.post(
        "/bookings",
        json=booking_payload(1),
        headers=headers,
    )

    list_response = client.get(
        "/bookings/me",
        headers=headers,
    )

    assert create_response.status_code == 403
    assert list_response.status_code == 403

def test_resource_owner_can_approve_booking_and_activity_is_logged(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Student Approval", "student-approval@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Owner Approval", "owner-approval@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    response = client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "APPROVED", "reason": "Request approved"},
        headers=owner,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "APPROVED"
    assert data["reason"] == "Request approved"

    db = TestingSession()
    try:
        booking = db.get(Booking, booking_id)
        assert booking.approved_by_id is not None
        assert booking.approved_at is not None

        log = db.scalar(
            select(ActivityLog).where(
                ActivityLog.entity_id == booking_id,
                ActivityLog.action == "BOOKING_APPROVED",
            )
        )
        assert log is not None
    finally:
        db.close()


def test_resource_owner_can_reject_booking(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Student Reject", "student-reject@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Owner Reject", "owner-reject@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    response = client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "REJECTED", "reason": "Unavailable"},
        headers=owner,
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "REJECTED"
    assert response.json()["data"]["reason"] == "Unavailable"


def test_admin_can_override_booking_decision(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Student Admin", "student-admin@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Owner Admin", "owner-admin@example.com", "OWNER"
    )
    admin = create_admin(TestingSession)

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    response = client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "APPROVED"},
        headers=admin,
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "APPROVED"


def test_student_cannot_decide_booking(test_context):
    client, _ = test_context

    student = register_user(
        client, "Student Cannot Decide", "student-no-decision@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Owner Cannot Decide", "owner-no-decision@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    response = client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "APPROVED"},
        headers=student,
    )

    assert response.status_code == 403


def test_different_owner_cannot_decide_booking(test_context):
    client, _ = test_context

    student = register_user(
        client, "Student Other Owner", "student-other-owner@example.com", "STUDENT"
    )
    owner_one = register_user(
        client, "Owner One", "owner-one-decision@example.com", "OWNER"
    )
    owner_two = register_user(
        client, "Owner Two", "owner-two-decision@example.com", "OWNER"
    )

    resource = create_resource(client, owner_one)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    response = client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "APPROVED"},
        headers=owner_two,
    )

    assert response.status_code == 403


def test_booking_cannot_be_decided_twice(test_context):
    client, _ = test_context

    student = register_user(
        client, "Student Twice", "student-twice@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Owner Twice", "owner-twice@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    first = client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "APPROVED"},
        headers=owner,
    )
    second = client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "REJECTED"},
        headers=owner,
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_approval_rechecks_eligibility(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Student Eligibility", "student-recheck@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Owner Eligibility", "owner-recheck@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    db = TestingSession()
    try:
        db.add(
            EligibilityRequirement(
                resource_id=resource["id"],
                requirement_type="CERTIFICATION",
                requirement_value="SAFETY",
                is_mandatory=True,
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "APPROVED"},
        headers=owner,
    )

    assert response.status_code == 403


def test_approval_rejects_overlapping_approved_booking(test_context):
    client, TestingSession = test_context

    student_one = register_user(
        client, "Student Overlap One", "student-overlap-one@example.com", "STUDENT"
    )
    student_two = register_user(
        client, "Student Overlap Two", "student-overlap-two@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Owner Overlap", "owner-overlap@example.com", "OWNER"
    )

    resource = create_resource(client, owner)

    first_payload = booking_payload(resource["id"])
    first = client.post(
        "/bookings", json=first_payload, headers=student_one
    )
    assert first.status_code == 201

    first_id = first.json()["data"]["id"]
    approved = client.patch(
        f"/bookings/{first_id}/decision",
        json={"decision": "APPROVED"},
        headers=owner,
    )
    assert approved.status_code == 200

    second_payload = {
        **first_payload,
        "purpose": "Second academic project",
    }
    second = client.post(
        "/bookings", json=second_payload, headers=student_two
    )
    assert second.status_code == 201

    second_id = second.json()["data"]["id"]
    response = client.patch(
        f"/bookings/{second_id}/decision",
        json={"decision": "APPROVED"},
        headers=owner,
    )

    assert response.status_code == 409

def test_student_can_view_own_booking_detail(test_context):
    client, _ = test_context

    student = register_user(
        client, "Detail Student", "detail-student@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Detail Owner", "detail-owner@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    response = client.get(
        f"/bookings/{booking_id}",
        headers=student,
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == booking_id


def test_student_cannot_view_another_students_booking(test_context):
    client, _ = test_context

    student_one = register_user(
        client, "Detail Student One", "detail-one@example.com", "STUDENT"
    )
    student_two = register_user(
        client, "Detail Student Two", "detail-two@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Detail Owner Two", "detail-owner-two@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student_one,
    )
    booking_id = created.json()["data"]["id"]

    response = client.get(
        f"/bookings/{booking_id}",
        headers=student_two,
    )

    assert response.status_code == 403


def test_resource_owner_can_view_booking_detail(test_context):
    client, _ = test_context

    student = register_user(
        client, "Detail Student Three", "detail-three@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Detail Owner Three", "detail-owner-three@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    response = client.get(
        f"/bookings/{booking_id}",
        headers=owner,
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == booking_id


def test_admin_can_view_booking_detail(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Detail Student Four", "detail-four@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Detail Owner Four", "detail-owner-four@example.com", "OWNER"
    )
    admin = create_admin(TestingSession)

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    response = client.get(
        f"/bookings/{booking_id}",
        headers=admin,
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == booking_id

def test_unrelated_owner_cannot_view_booking_detail(test_context):
    client, _ = test_context

    student = register_user(
        client, "Detail Student Five", "detail-five@example.com", "STUDENT"
    )
    owner_one = register_user(
        client, "Detail Owner Five", "detail-owner-five@example.com", "OWNER"
    )
    owner_two = register_user(
        client, "Unrelated Owner", "unrelated-owner@example.com", "OWNER"
    )

    resource = create_resource(client, owner_one)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    response = client.get(
        f"/bookings/{booking_id}",
        headers=owner_two,
    )

    assert response.status_code == 403


def test_missing_booking_detail_returns_404(test_context):
    client, _ = test_context

    student = register_user(
        client, "Missing Detail Student", "missing-detail@example.com", "STUDENT"
    )

    response = client.get(
        "/bookings/999999",
        headers=student,
    )

    assert response.status_code == 404

def test_student_can_submit_initial_condition_report(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Condition Student", "condition-student@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Condition Owner", "condition-owner@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    approved = client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "APPROVED"},
        headers=owner,
    )
    assert approved.status_code == 200

    response = client.post(
        f"/bookings/{booking_id}/condition-reports/initial",
        json={
            "condition_description": "Device received in good condition",
            "evidence_reference": "initial-photo-001",
        },
        headers=student,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["report_type"] == "INITIAL"
    assert data["submitted_by_id"] == int(
        client.get("/bookings/me", headers=student).json()["data"][0]["user_id"]
    )

    db = TestingSession()
    try:
        report = db.get(ConditionReport, data["id"])
        assert report is not None

        log = db.scalar(
            select(ActivityLog).where(
                ActivityLog.entity_id == booking_id,
                ActivityLog.action == "BOOKING_CONDITION_REPORT_INITIAL",
            )
        )
        assert log is not None
    finally:
        db.close()


def test_owner_can_submit_final_condition_report(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Final Student", "final-student@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Final Owner", "final-owner@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    db = TestingSession()
    try:
        booking = db.get(Booking, booking_id)
        booking.status = BookingStatus.IN_USE
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/bookings/{booking_id}/condition-reports/final",
        json={
            "condition_description": "Device returned in good condition",
            "evidence_reference": "final-photo-001",
        },
        headers=owner,
    )

    assert response.status_code == 201
    assert response.json()["data"]["report_type"] == "FINAL"


def test_duplicate_initial_condition_report_is_rejected(test_context):
    client, _ = test_context

    student = register_user(
        client, "Duplicate Student", "duplicate-report@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Duplicate Owner", "duplicate-owner@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "APPROVED"},
        headers=owner,
    )

    payload = {
        "condition_description": "Device received in good condition"
    }

    first = client.post(
        f"/bookings/{booking_id}/condition-reports/initial",
        json=payload,
        headers=student,
    )
    second = client.post(
        f"/bookings/{booking_id}/condition-reports/initial",
        json=payload,
        headers=student,
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_initial_report_requires_approved_booking(test_context):
    client, _ = test_context

    student = register_user(
        client, "Pending Student", "pending-report@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Pending Owner", "pending-owner@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    response = client.post(
        f"/bookings/{booking_id}/condition-reports/initial",
        json={"condition_description": "Device condition checked"},
        headers=student,
    )

    assert response.status_code == 409


def test_final_report_requires_in_use_booking(test_context):
    client, _ = test_context

    student = register_user(
        client, "Approved Student", "approved-report@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Approved Owner", "approved-owner@example.com", "OWNER"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "APPROVED"},
        headers=owner,
    )

    response = client.post(
        f"/bookings/{booking_id}/condition-reports/final",
        json={"condition_description": "Device returned safely"},
        headers=student,
    )

    assert response.status_code == 409


def test_unrelated_user_cannot_submit_condition_report(test_context):
    client, _ = test_context

    student = register_user(
        client, "Report Student", "report-student@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Report Owner", "report-owner@example.com", "OWNER"
    )
    unrelated = register_user(
        client, "Unrelated Student", "unrelated-report@example.com", "STUDENT"
    )

    resource = create_resource(client, owner)
    created = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    booking_id = created.json()["data"]["id"]

    client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "APPROVED"},
        headers=owner,
    )

    response = client.post(
        f"/bookings/{booking_id}/condition-reports/initial",
        json={"condition_description": "Attempted unauthorized report"},
        headers=unrelated,
    )

    assert response.status_code == 403

def test_owner_can_view_bookings_for_own_resources(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Student One", "owner_test_student1@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Owner One", "owner_test_owner1@example.com", "OWNER"
    )

    resource = create_resource(client, owner, title="Owner One Projector")

    booking_response = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    assert booking_response.status_code == 201

    response = client.get("/bookings/owner", headers=owner)

    assert response.status_code == 200
    body = response.json()

    assert body["success"] is True
    assert len(body["data"]) == 1
    assert body["data"][0]["resource_id"] == resource["id"]


def test_owner_cannot_view_another_owners_bookings(test_context):
    client, _ = test_context

    student = register_user(
        client, "Student Two", "owner_test_student2@example.com", "STUDENT"
    )
    owner_one = register_user(
        client, "Owner One", "owner_test_owner2@example.com", "OWNER"
    )
    owner_two = register_user(
        client, "Owner Two", "owner_test_owner3@example.com", "OWNER"
    )

    resource = create_resource(client, owner_one, title="Owner One Camera")

    booking_response = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    assert booking_response.status_code == 201

    response = client.get("/bookings/owner", headers=owner_two)

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_owner_booking_list_returns_empty_list_when_no_bookings(test_context):
    client, _ = test_context

    owner = register_user(
        client, "Owner Empty", "owner_test_empty@example.com", "OWNER"
    )

    response = client.get("/bookings/owner", headers=owner)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"] == []


def test_student_cannot_access_owner_booking_list(test_context):
    client, _ = test_context

    student = register_user(
        client, "Student Three", "owner_test_student3@example.com", "STUDENT"
    )

    response = client.get("/bookings/owner", headers=student)

    assert response.status_code == 403

def create_approved_booking(client, student, owner):
    resource = create_resource(client, owner, title="Lifecycle Test Resource")

    response = client.post(
        "/bookings",
        json=booking_payload(resource["id"]),
        headers=student,
    )
    assert response.status_code == 201

    booking_id = response.json()["data"]["id"]

    decision = client.patch(
        f"/bookings/{booking_id}/decision",
        json={"decision": "APPROVED"},
        headers=owner,
    )
    assert decision.status_code == 200

    return booking_id


def submit_condition_report(client, booking_id, headers, report_type):
    return client.post(
        f"/bookings/{booking_id}/condition-reports/{report_type.lower()}",
        json={"condition_description": f"{report_type} condition verified"},
        headers=headers,
    )


def test_student_can_check_in_with_initial_report(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Checkin Student", "checkin_student1@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Checkin Owner", "checkin_owner1@example.com", "OWNER"
    )

    booking_id = create_approved_booking(client, student, owner)

    report = submit_condition_report(client, booking_id, student, "INITIAL")
    assert report.status_code == 201

    response = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=student,
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "IN_USE"
    assert response.json()["data"]["checkin_at"] is not None

    db = TestingSession()
    try:
        log = db.scalar(
            select(ActivityLog).where(
                ActivityLog.entity_id == booking_id,
                ActivityLog.action == "BOOKING_CHECKED_IN",
            )
        )
        assert log is not None
    finally:
        db.close()


def test_owner_can_check_in_with_initial_report(test_context):
    client, _ = test_context

    student = register_user(
        client, "Owner Checkin Student", "checkin_student2@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Owner Checkin Owner", "checkin_owner2@example.com", "OWNER"
    )

    booking_id = create_approved_booking(client, student, owner)

    report = submit_condition_report(client, booking_id, owner, "INITIAL")
    assert report.status_code == 201

    response = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=owner,
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "IN_USE"


def test_check_in_requires_initial_report(test_context):
    client, _ = test_context

    student = register_user(
        client, "Missing Report Student", "checkin_student3@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Missing Report Owner", "checkin_owner3@example.com", "OWNER"
    )

    booking_id = create_approved_booking(client, student, owner)

    response = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=student,
    )

    assert response.status_code == 409


def test_student_can_check_out_with_final_report(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Checkout Student", "checkout_student1@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Checkout Owner", "checkout_owner1@example.com", "OWNER"
    )

    booking_id = create_approved_booking(client, student, owner)

    initial = submit_condition_report(client, booking_id, student, "INITIAL")
    assert initial.status_code == 201

    checkin = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=student,
    )
    assert checkin.status_code == 200

    final = submit_condition_report(client, booking_id, student, "FINAL")
    assert final.status_code == 201

    response = client.post(
        f"/bookings/{booking_id}/check-out",
        headers=student,
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "RETURNED"
    assert response.json()["data"]["checkout_at"] is not None

    db = TestingSession()
    try:
        log = db.scalar(
            select(ActivityLog).where(
                ActivityLog.entity_id == booking_id,
                ActivityLog.action == "BOOKING_CHECKED_OUT",
            )
        )
        assert log is not None
    finally:
        db.close()


def test_check_out_requires_final_report(test_context):
    client, _ = test_context

    student = register_user(
        client, "No Final Student", "checkout_student2@example.com", "STUDENT"
    )
    owner = register_user(
        client, "No Final Owner", "checkout_owner2@example.com", "OWNER"
    )

    booking_id = create_approved_booking(client, student, owner)

    initial = submit_condition_report(client, booking_id, student, "INITIAL")
    assert initial.status_code == 201

    checkin = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=student,
    )
    assert checkin.status_code == 200

    response = client.post(
        f"/bookings/{booking_id}/check-out",
        headers=student,
    )

    assert response.status_code == 409


def test_unrelated_user_cannot_check_in_or_check_out(test_context):
    client, _ = test_context

    student = register_user(
        client, "Access Student", "checkout_student3@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Access Owner", "checkout_owner3@example.com", "OWNER"
    )
    unrelated = register_user(
        client, "Unrelated User", "checkout_unrelated@example.com", "STUDENT"
    )

    booking_id = create_approved_booking(client, student, owner)

    initial = submit_condition_report(client, booking_id, student, "INITIAL")
    assert initial.status_code == 201

    checkin = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=unrelated,
    )
    assert checkin.status_code == 403

    checkin = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=student,
    )
    assert checkin.status_code == 200

    final = submit_condition_report(client, booking_id, student, "FINAL")
    assert final.status_code == 201

    checkout = client.post(
        f"/bookings/{booking_id}/check-out",
        headers=unrelated,
    )
    assert checkout.status_code == 403


def test_duplicate_check_in_and_check_out_are_rejected(test_context):
    client, _ = test_context

    student = register_user(
        client, "Duplicate Student", "duplicate_student@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Duplicate Owner", "duplicate_owner@example.com", "OWNER"
    )

    booking_id = create_approved_booking(client, student, owner)

    initial = submit_condition_report(client, booking_id, student, "INITIAL")
    assert initial.status_code == 201

    first_checkin = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=student,
    )
    assert first_checkin.status_code == 200

    second_checkin = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=student,
    )
    assert second_checkin.status_code == 409

    final = submit_condition_report(client, booking_id, student, "FINAL")
    assert final.status_code == 201

    first_checkout = client.post(
        f"/bookings/{booking_id}/check-out",
        headers=student,
    )
    assert first_checkout.status_code == 200

    second_checkout = client.post(
        f"/bookings/{booking_id}/check-out",
        headers=student,
    )
    assert second_checkout.status_code == 409


def test_checkin_checkout_activity_logs_record_actual_actor(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Actor Student", "actor_student@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Actor Owner", "actor_owner@example.com", "OWNER"
    )

    booking_id = create_approved_booking(client, student, owner)

    initial = submit_condition_report(client, booking_id, owner, "INITIAL")
    assert initial.status_code == 201

    checkin = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=owner,
    )
    assert checkin.status_code == 200

    final = submit_condition_report(client, booking_id, owner, "FINAL")
    assert final.status_code == 201

    checkout = client.post(
        f"/bookings/{booking_id}/check-out",
        headers=owner,
    )
    assert checkout.status_code == 200

    db = TestingSession()
    try:
        logs = db.scalars(
            select(ActivityLog).where(
                ActivityLog.entity_id == booking_id,
                ActivityLog.action.in_([
                    "BOOKING_CHECKED_IN",
                    "BOOKING_CHECKED_OUT",
                ]),
            )
        ).all()

        assert len(logs) == 2

        for log in logs:
            assert log.actor_id is not None
    finally:
        db.close()

def test_admin_can_check_in_and_check_out(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Admin Flow Student", "admin_flow_student@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Admin Flow Owner", "admin_flow_owner@example.com", "OWNER"
    )
    admin = create_admin(TestingSession)

    booking_id = create_approved_booking(client, student, owner)

    initial = submit_condition_report(client, booking_id, student, "INITIAL")
    assert initial.status_code == 201

    checkin = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=admin,
    )
    assert checkin.status_code == 200
    assert checkin.json()["data"]["status"] == "IN_USE"

    final = submit_condition_report(client, booking_id, owner, "FINAL")
    assert final.status_code == 201

    checkout = client.post(
        f"/bookings/{booking_id}/check-out",
        headers=admin,
    )
    assert checkout.status_code == 200
    assert checkout.json()["data"]["status"] == "RETURNED"


def test_checkin_and_checkout_return_404_for_missing_booking(test_context):
    client, _ = test_context

    student = register_user(
        client, "Missing Booking Student", "missing_booking_student@example.com", "STUDENT"
    )

    checkin = client.post("/bookings/99999/check-in", headers=student)
    checkout = client.post("/bookings/99999/check-out", headers=student)

    assert checkin.status_code == 404
    assert checkout.status_code == 404


def test_failed_checkin_does_not_change_booking_state(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Rollback Student", "rollback_student@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Rollback Owner", "rollback_owner@example.com", "OWNER"
    )

    booking_id = create_approved_booking(client, student, owner)

    response = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=student,
    )
    assert response.status_code == 409

    db = TestingSession()
    try:
        booking = db.get(Booking, booking_id)
        assert booking.status == BookingStatus.APPROVED
        assert booking.checkin_at is None
    finally:
        db.close()


def test_activity_logs_record_exact_checkin_checkout_actor(test_context):
    client, TestingSession = test_context

    student = register_user(
        client, "Exact Actor Student", "exact_actor_student@example.com", "STUDENT"
    )
    owner = register_user(
        client, "Exact Actor Owner", "exact_actor_owner@example.com", "OWNER"
    )

    booking_id = create_approved_booking(client, student, owner)

    initial = submit_condition_report(client, booking_id, owner, "INITIAL")
    assert initial.status_code == 201

    checkin = client.post(
        f"/bookings/{booking_id}/check-in",
        headers=owner,
    )
    assert checkin.status_code == 200

    final = submit_condition_report(client, booking_id, owner, "FINAL")
    assert final.status_code == 201

    checkout = client.post(
        f"/bookings/{booking_id}/check-out",
        headers=owner,
    )
    assert checkout.status_code == 200

    db = TestingSession()
    try:
        for action in ("BOOKING_CHECKED_IN", "BOOKING_CHECKED_OUT"):
            log = db.scalar(
                select(ActivityLog).where(
                    ActivityLog.entity_id == booking_id,
                    ActivityLog.action == action,
                )
            )
            assert log is not None
            assert log.actor_id is not None

            actor = db.get(User, log.actor_id)
            assert actor is not None
            assert actor.id == log.actor_id
            assert actor.id == db.scalar(
                select(Resource.owner_id)
                .join(Booking, Booking.resource_id == Resource.id)
                .where(Booking.id == booking_id)
            )
    finally:
        db.close()