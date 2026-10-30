import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.booking import Booking
from app.models.enums import BookingStatus
from app.models.resource import Resource
from app.schemas.booking import BookingCreate
from app.services.eligibility_service import check_resource_eligibility
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.booking import BookingDecision
from app.models.condition_report import ConditionReport
from app.schemas.booking import ConditionReportCreate

def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive and timezone-aware datetimes to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _validate_resource_window(
    resource: Resource,
    start_at: datetime,
    end_at: datetime,
) -> None:
    if not resource.is_active:
        raise ValueError("Resource is not active")

    if resource.available_from is not None:
        if _as_utc(start_at) < _as_utc(resource.available_from):
            raise ValueError(
                "Booking starts before the resource availability window"
            )

    if resource.available_until is not None:
        if _as_utc(end_at) > _as_utc(resource.available_until):
            raise ValueError(
                "Booking ends after the resource availability window"
            )


def create_booking(
    db: Session,
    user_id: int,
    booking_data: BookingCreate,
) -> Booking:
    resource = db.get(Resource, booking_data.resource_id)

    if resource is None:
        raise LookupError("Resource not found")

    _validate_resource_window(
        resource,
        booking_data.start_at,
        booking_data.end_at,
    )

    eligibility = check_resource_eligibility(
        db,
        user_id,
        resource.id,
    )

    if eligibility is None:
        raise ValueError("Resource is not available")

    if not eligibility.eligible:
        raise PermissionError("You do not meet the resource eligibility requirements")

    booking = Booking(
        student_id=user_id,
        resource_id=resource.id,
        start_at=booking_data.start_at,
        end_at=booking_data.end_at,
        purpose=booking_data.purpose.strip(),
        status=BookingStatus.PENDING,
    )

    try:
        db.add(booking)
        db.flush()

        activity = ActivityLog(
            actor_id=user_id,
            action="BOOKING_CREATED",
            entity_type="BOOKING",
            entity_id=booking.id,
            details=json.dumps({
                "resource_id": resource.id,
                "start_at": booking.start_at.isoformat(),
                "end_at": booking.end_at.isoformat(),
                "status": BookingStatus.PENDING.value,
            }),
        )
        db.add(activity)

        db.commit()
        db.refresh(booking)
        return booking

    except Exception:
        db.rollback()
        raise


def get_my_bookings(
    db: Session,
    user_id: int,
) -> list[Booking]:
    statement = (
        select(Booking)
        .where(Booking.student_id == user_id)
        .order_by(Booking.created_at.desc(), Booking.id.desc())
    )
    return list(db.scalars(statement).all())

def get_owner_bookings(
    db: Session,
    owner_id: int,
) -> list[Booking]:
    statement = (
        select(Booking)
        .join(Resource, Booking.resource_id == Resource.id)
        .where(Resource.owner_id == owner_id)
        .order_by(Booking.created_at.desc(), Booking.id.desc())
    )

    return list(db.scalars(statement).all())


def decide_booking(
    db: Session,
    booking_id: int,
    actor: User,
    decision_data: BookingDecision,
) -> Booking:
    try:
        booking = db.get(Booking, booking_id)

        if booking is None:
            raise LookupError("Booking not found")

        resource = db.get(Resource, booking.resource_id)

        if resource is None:
            raise LookupError("Resource not found")

        if booking.status != BookingStatus.PENDING:
            raise RuntimeError("Only pending bookings can be decided")

        if booking.student_id == actor.id:
            raise PermissionError("You cannot decide your own booking")

        if actor.role != UserRole.ADMIN and resource.owner_id != actor.id:
            raise PermissionError("You are not allowed to decide this booking")

        if decision_data.decision == "APPROVED":
            _validate_resource_window(
                resource,
                booking.start_at,
                booking.end_at,
            )

            eligibility = check_resource_eligibility(
                db,
                booking.student_id,
                resource.id,
            )

            if eligibility is None or not eligibility.eligible:
                raise PermissionError(
                    "Student no longer meets the resource eligibility requirements"
                )

            overlap_statement = select(Booking).where(
                Booking.resource_id == booking.resource_id,
                Booking.id != booking.id,
                Booking.status.in_([
                    BookingStatus.APPROVED,
                    BookingStatus.IN_USE,
                ]),
                Booking.start_at < booking.end_at,
                Booking.end_at > booking.start_at,
            )

            conflicting_booking = db.scalar(overlap_statement)

            if conflicting_booking is not None:
                raise ValueError(
                    "Resource already has an overlapping approved or active booking"
                )

            booking.status = BookingStatus.APPROVED
            booking.approved_by_id = actor.id
            booking.approved_at = datetime.now(timezone.utc)
            action = "BOOKING_APPROVED"

        else:
            booking.status = BookingStatus.REJECTED
            action = "BOOKING_REJECTED"

        booking.decision_note = (
            decision_data.reason.strip()
            if decision_data.reason
            else None
        )

        db.add(
            ActivityLog(
                actor_id=actor.id,
                action=action,
                entity_type="BOOKING",
                entity_id=booking.id,
                details=json.dumps({
                    "previous_status": BookingStatus.PENDING.value,
                    "new_status": booking.status.value,
                    "reason": booking.decision_note,
                }),
            )
        )

        db.commit()
        db.refresh(booking)
        return booking

    except Exception:
        db.rollback()
        raise

def get_booking_by_id(
    db: Session,
    booking_id: int,
    actor: User,
) -> Booking:
    booking = db.get(Booking, booking_id)

    if booking is None:
        raise LookupError("Booking not found")

    resource = db.get(Resource, booking.resource_id)

    if resource is None:
        raise LookupError("Resource not found")

    is_admin = actor.role == UserRole.ADMIN
    is_student = booking.student_id == actor.id
    is_owner = resource.owner_id == actor.id

    if not (is_admin or is_student or is_owner):
        raise PermissionError("You are not allowed to view this booking")

    return booking

def create_condition_report(
    db: Session,
    booking_id: int,
    actor: User,
    report_type: str,
    report_data: ConditionReportCreate,
) -> ConditionReport:
    try:
        if report_type not in ("INITIAL", "FINAL"):
            raise ValueError("Invalid condition report type")

        booking = db.get(Booking, booking_id)

        if booking is None:
            raise LookupError("Booking not found")

        resource = db.get(Resource, booking.resource_id)

        if resource is None:
            raise LookupError("Resource not found")

        is_admin = actor.role == UserRole.ADMIN
        is_student = booking.student_id == actor.id
        is_owner = resource.owner_id == actor.id

        if not (is_admin or is_student or is_owner):
            raise PermissionError(
                "You are not allowed to submit a report for this booking"
            )

        if report_type == "INITIAL":
            if booking.status != BookingStatus.APPROVED:
                raise RuntimeError(
                    "Initial condition report requires an approved booking"
                )
        else:
            if booking.status != BookingStatus.IN_USE:
                raise RuntimeError(
                    "Final condition report requires an active booking"
                )

        duplicate_statement = select(ConditionReport).where(
            ConditionReport.booking_id == booking_id,
            ConditionReport.submitted_by_id == actor.id,
            ConditionReport.report_type == report_type,
        )

        existing_report = db.scalar(duplicate_statement)

        if existing_report is not None:
            raise RuntimeError(
                "You have already submitted this condition report"
            )

        report = ConditionReport(
            booking_id=booking_id,
            submitted_by_id=actor.id,
            report_type=report_type,
            condition_description=report_data.condition_description.strip(),
            evidence_reference=report_data.evidence_reference,
        )

        db.add(report)
        db.flush()

        db.add(
            ActivityLog(
                actor_id=actor.id,
                action=f"BOOKING_CONDITION_REPORT_{report_type}",
                entity_type="BOOKING",
                entity_id=booking_id,
                details=json.dumps({
                    "report_id": report.id,
                    "report_type": report_type,
                }),
            )
        )

        db.commit()
        db.refresh(report)
        return report

    except Exception:
        db.rollback()
        raise

def check_in_booking(
    db: Session,
    booking_id: int,
    actor: User,
) -> Booking:
    try:
        booking = db.get(Booking, booking_id)

        if booking is None:
            raise LookupError("Booking not found")

        resource = db.get(Resource, booking.resource_id)

        if resource is None:
            raise LookupError("Resource not found")

        is_admin = actor.role == UserRole.ADMIN
        is_student = booking.student_id == actor.id
        is_owner = resource.owner_id == actor.id

        if not (is_admin or is_student or is_owner):
            raise PermissionError(
                "You are not allowed to check in this booking"
            )

        if booking.status != BookingStatus.APPROVED:
            raise RuntimeError(
                "Only approved bookings can be checked in"
            )

        initial_report = db.scalar(
            select(ConditionReport.id).where(
                ConditionReport.booking_id == booking_id,
                ConditionReport.report_type == "INITIAL",
            ).limit(1)
        )

        if initial_report is None:
            raise RuntimeError(
                "Initial condition report is required before check-in"
            )

        booking.status = BookingStatus.IN_USE
        booking.checkin_at = datetime.now(timezone.utc)

        db.add(
            ActivityLog(
                actor_id=actor.id,
                action="BOOKING_CHECKED_IN",
                entity_type="BOOKING",
                entity_id=booking.id,
                details=json.dumps({
                    "previous_status": BookingStatus.APPROVED.value,
                    "new_status": BookingStatus.IN_USE.value,
                }),
            )
        )

        db.commit()
        db.refresh(booking)

        return booking

    except Exception:
        db.rollback()
        raise

def check_out_booking(
    db: Session,
    booking_id: int,
    actor: User,
) -> Booking:
    try:
        booking = db.get(Booking, booking_id)

        if booking is None:
            raise LookupError("Booking not found")

        resource = db.get(Resource, booking.resource_id)

        if resource is None:
            raise LookupError("Resource not found")

        is_admin = actor.role == UserRole.ADMIN
        is_student = booking.student_id == actor.id
        is_owner = resource.owner_id == actor.id

        if not (is_admin or is_student or is_owner):
            raise PermissionError(
                "You are not allowed to check out this booking"
            )

        if booking.status != BookingStatus.IN_USE:
            raise RuntimeError(
                "Only active bookings can be checked out"
            )

        final_report = db.scalar(
            select(ConditionReport.id).where(
                ConditionReport.booking_id == booking_id,
                ConditionReport.report_type == "FINAL",
            ).limit(1)
        )

        if final_report is None:
            raise RuntimeError(
                "Final condition report is required before check-out"
            )

        booking.status = BookingStatus.RETURNED
        booking.checkout_at = datetime.now(timezone.utc)

        db.add(
            ActivityLog(
                actor_id=actor.id,
                action="BOOKING_CHECKED_OUT",
                entity_type="BOOKING",
                entity_id=booking.id,
                details=json.dumps({
                    "previous_status": BookingStatus.IN_USE.value,
                    "new_status": BookingStatus.RETURNED.value,
                }),
            )
        )

        db.commit()
        db.refresh(booking)

        return booking

    except Exception:
        db.rollback()
        raise