from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.booking import Booking
from app.models.booking_baseline_snapshot import (
    BookingBaselineSnapshot,
    BookingBaselineSnapshotImage,
)
from app.models.enums import BookingStatus, ResourceType, UserRole
from app.models.resource import Resource
from app.models.resource_baseline_image import ResourceBaselineImage
from app.models.user import User
from app.services.booking_baseline_snapshot_service import (
    IncompleteResourceBaselineError,
    SnapshotAccessDeniedError,
    SnapshotRequiresApprovedBookingError,
    create_booking_baseline_snapshot,
    stage_booking_baseline_snapshot,
    validate_resource_baseline,
    SnapshotIntegrityError,
    get_booking_baseline_snapshot,
)
from app.services.baseline_snapshot_adapter import snapshot_records_to_angle_bytes
from app.services.resource_baseline_service import (
    BaselineAccessDeniedError,
    BaselineImageTooLargeError,
    DuplicateBaselineAngleError,
    InvalidBaselineAngleError,
    InvalidBaselineImageError,
    UnsupportedBaselineImageTypeError,
    create_resource_baseline_image,
    list_resource_baseline_images,
    replace_resource_baseline_image,
)
from cv_engine.angles import REQUIRED_ANGLES
from cv_engine.quality import MAX_IMAGE_BYTES


def make_image_bytes(color=(80, 120, 160), image_format="PNG") -> bytes:
    image = Image.new("RGB", (320, 320), color)
    buffer = BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()


@pytest.fixture
def baseline_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with Session() as db:
        users = {
            "owner": User(
                full_name="Baseline Owner",
                email="baseline-owner@example.com",
                hashed_password="unused",
                role=UserRole.OWNER,
                is_active=True,
            ),
            "admin": User(
                full_name="Baseline Admin",
                email="baseline-admin@example.com",
                hashed_password="unused",
                role=UserRole.ADMIN,
                is_active=True,
            ),
            "student": User(
                full_name="Baseline Student",
                email="baseline-student@example.com",
                hashed_password="unused",
                role=UserRole.STUDENT,
                is_active=True,
            ),
        }
        db.add_all(users.values())
        db.flush()

        resource = Resource(
            owner_id=users["owner"].id,
            title="Baseline Camera",
            description="Resource baseline test fixture",
            category="equipment",
            resource_type=ResourceType.EQUIPMENT,
            location="Lab",
            is_active=True,
        )
        db.add(resource)
        db.flush()
        now = datetime.now(timezone.utc)
        booking = Booking(
            student_id=users["student"].id,
            resource_id=resource.id,
            start_at=now,
            end_at=now + timedelta(hours=1),
            purpose="Baseline snapshot test",
            status=BookingStatus.APPROVED,
        )
        db.add(booking)
        db.commit()

    try:
        yield Session, users, resource, booking
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def add_baseline(db, resource, actor, angle, image_data=None, mime_type="image/png"):
    return create_resource_baseline_image(
        db,
        resource_id=resource.id,
        actor=actor,
        angle=angle,
        filename=f"{angle.lower()}.png",
        declared_mime_type=mime_type,
        image_data=image_data or make_image_bytes(),
    )


def add_all_baselines(db, resource, actor):
    return {
        angle: add_baseline(
            db,
            resource,
            actor,
            angle,
            make_image_bytes((index * 20, 80, 140)),
        )
        for index, angle in enumerate(REQUIRED_ANGLES, start=1)
    }


def test_owner_creates_validated_baseline_with_sha256(baseline_context):
    Session, users, resource, _ = baseline_context
    image_data = make_image_bytes()
    with Session() as db:
        baseline = add_baseline(db, resource, users["owner"], "front", image_data)

        assert baseline.angle == "FRONT"
        assert baseline.mime_type == "image/png"
        assert baseline.byte_size == len(image_data)
        assert baseline.sha256 == sha256(image_data).hexdigest()
        assert baseline.image_data == image_data
        assert baseline.uploaded_by_id == users["owner"].id


@pytest.mark.parametrize("angle", ["DIAGONAL", "", "FRONT/../BACK"])
def test_invalid_baseline_angles_are_rejected(baseline_context, angle):
    Session, users, resource, _ = baseline_context
    with Session() as db, pytest.raises(InvalidBaselineAngleError):
        add_baseline(db, resource, users["owner"], angle)


def test_baseline_file_validation_rejects_mime_size_and_corrupt_content(baseline_context):
    Session, users, resource, _ = baseline_context
    with Session() as db:
        with pytest.raises(UnsupportedBaselineImageTypeError):
            add_baseline(
                db,
                resource,
                users["owner"],
                "FRONT",
                mime_type="image/jpeg",
            )
        with pytest.raises(InvalidBaselineImageError):
            add_baseline(
                db,
                resource,
                users["owner"],
                "FRONT",
                image_data=b"not an image",
            )
        with pytest.raises(BaselineImageTooLargeError):
            add_baseline(
                db,
                resource,
                users["owner"],
                "FRONT",
                image_data=b"x" * (MAX_IMAGE_BYTES + 1),
            )


def test_duplicate_requires_explicit_replacement_and_snapshots_stay_independent(
    baseline_context,
):
    Session, users, resource, booking = baseline_context
    with Session() as db:
        baselines = add_all_baselines(db, resource, users["owner"])
        original = baselines["FRONT"]
        original_bytes = original.image_data

        with pytest.raises(DuplicateBaselineAngleError):
            add_baseline(
                db,
                resource,
                users["owner"],
                "FRONT",
                make_image_bytes((200, 0, 0)),
            )

        snapshot = create_booking_baseline_snapshot(
            db, booking_id=booking.id, actor=users["owner"]
        )
        replacement_bytes = make_image_bytes((0, 200, 0))
        replaced = replace_resource_baseline_image(
            db,
            resource_id=resource.id,
            actor=users["owner"],
            angle="FRONT",
            filename="replacement.png",
            declared_mime_type="image/png",
            image_data=replacement_bytes,
        )

        snapshot_front = db.scalar(
            select(BookingBaselineSnapshotImage).where(
                BookingBaselineSnapshotImage.snapshot_id == snapshot.id,
                BookingBaselineSnapshotImage.angle == "FRONT",
            )
        )
        assert replaced.id == original.id
        assert replaced.image_data == replacement_bytes
        assert snapshot_front is not None
        assert snapshot_front.image_data == original_bytes
        assert snapshot_front.sha256 == sha256(original_bytes).hexdigest()


def test_only_resource_owner_or_admin_can_manage_baselines(baseline_context):
    Session, users, resource, _ = baseline_context
    with Session() as db:
        with pytest.raises(BaselineAccessDeniedError):
            add_baseline(db, resource, users["student"], "FRONT")

        add_baseline(db, resource, users["admin"], "FRONT")
        assert len(
            list_resource_baseline_images(
                db, resource_id=resource.id, actor=users["owner"]
            )
        ) == 1


def test_snapshot_rejects_incomplete_baselines_with_missing_angles(baseline_context):
    Session, users, resource, booking = baseline_context
    with Session() as db:
        add_baseline(db, resource, users["owner"], "FRONT")

        with pytest.raises(IncompleteResourceBaselineError) as exc_info:
            create_booking_baseline_snapshot(
                db, booking_id=booking.id, actor=users["owner"]
            )

        assert exc_info.value.missing_angles == list(REQUIRED_ANGLES[1:])
        assert db.scalar(select(BookingBaselineSnapshot)) is None


def test_validation_reports_missing_angles_and_invalid_content(baseline_context):
    Session, users, resource, booking = baseline_context
    with Session() as db:
        add_all_baselines(db, resource, users["owner"])
        damaged = db.scalar(
            select(ResourceBaselineImage).where(
                ResourceBaselineImage.angle == "LEFT"
            )
        )
        damaged.image_data = b"corrupt"
        db.commit()

        result = validate_resource_baseline(db, resource_id=resource.id)
        assert result["missing_angles"] == []
        assert "LEFT" in result["invalid_angles"]
        with pytest.raises(IncompleteResourceBaselineError) as exc_info:
            stage_booking_baseline_snapshot(
                db, booking_id=booking.id, actor=users["owner"]
            )
        assert "LEFT" in exc_info.value.invalid_angles
        assert db.scalar(select(BookingBaselineSnapshot)) is None


def test_complete_snapshot_staging_does_not_commit_and_reader_verifies_integrity(
    baseline_context,
):
    Session, users, resource, booking = baseline_context
    with Session() as db:
        add_all_baselines(db, resource, users["owner"])
        snapshot = stage_booking_baseline_snapshot(
            db, booking_id=booking.id, actor=users["owner"]
        )
        assert db.in_transaction()
        db.rollback()
        assert db.scalar(select(BookingBaselineSnapshot)) is None

        create_booking_baseline_snapshot(db, booking_id=booking.id, actor=users["owner"])
        snapshot = get_booking_baseline_snapshot(
            db, booking_id=booking.id, actor=users["student"]
        )
        image = db.scalar(
            select(BookingBaselineSnapshotImage).where(
                BookingBaselineSnapshotImage.snapshot_id == snapshot.id
            )
        )
        db.execute(
            text(
                "UPDATE booking_baseline_snapshot_images "
                "SET image_data=:data WHERE id=:image_id"
            ),
            {"data": b"tampered", "image_id": image.id},
        )
        db.commit()
        db.expire_all()
        with pytest.raises(SnapshotIntegrityError):
            get_booking_baseline_snapshot(db, booking_id=booking.id, actor=users["student"])


def test_snapshot_is_atomic_complete_and_idempotent_on_retry(baseline_context):
    Session, users, resource, booking = baseline_context
    with Session() as db:
        baselines = add_all_baselines(db, resource, users["owner"])

        first = create_booking_baseline_snapshot(
            db, booking_id=booking.id, actor=users["owner"]
        )
        images = list(
            db.scalars(
                select(BookingBaselineSnapshotImage).where(
                    BookingBaselineSnapshotImage.snapshot_id == first.id
                )
            ).all()
        )
        second = create_booking_baseline_snapshot(
            db, booking_id=booking.id, actor=users["owner"]
        )

        assert first.id == second.id
        assert len(images) == len(REQUIRED_ANGLES)
        assert {image.angle for image in images} == set(REQUIRED_ANGLES)
        assert {image.source_baseline_image_id for image in images} == {
            baseline.id for baseline in baselines.values()
        }
        assert all(image.image_data for image in images)


def test_snapshot_records_adapt_to_angle_to_bytes_mapping(baseline_context):
    Session, users, resource, booking = baseline_context
    with Session() as db:
        add_all_baselines(db, resource, users["owner"])
        snapshot = create_booking_baseline_snapshot(
            db, booking_id=booking.id, actor=users["owner"]
        )
        rows = list(
            db.scalars(
                select(BookingBaselineSnapshotImage).where(
                    BookingBaselineSnapshotImage.snapshot_id == snapshot.id
                )
            ).all()
        )
        image_map = snapshot_records_to_angle_bytes(rows)

        assert set(image_map) == set(REQUIRED_ANGLES)
        assert all(isinstance(payload, bytes) for payload in image_map.values())
        assert image_map["FRONT"] == next(
            image.image_data for image in rows if image.angle == "FRONT"
        )


def test_snapshot_rows_cannot_be_updated_or_deleted_through_orm(baseline_context):
    Session, users, resource, booking = baseline_context
    with Session() as db:
        add_all_baselines(db, resource, users["owner"])
        snapshot = create_booking_baseline_snapshot(
            db, booking_id=booking.id, actor=users["owner"]
        )
        image = db.scalar(
            select(BookingBaselineSnapshotImage).where(
                BookingBaselineSnapshotImage.snapshot_id == snapshot.id
            )
        )
        original_filename = image.original_filename
        image.original_filename = "mutated.png"
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()

        image = db.get(BookingBaselineSnapshotImage, image.id)
        assert image.original_filename == original_filename
        db.delete(image)
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()

        stored_snapshot = db.get(BookingBaselineSnapshot, snapshot.id)
        stored_snapshot.created_by_id = users["admin"].id
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()


def test_snapshot_does_not_leave_partial_rows_when_insert_fails(baseline_context):
    Session, users, resource, booking = baseline_context
    with Session() as db:
        add_all_baselines(db, resource, users["owner"])
        db.execute(
            text(
                """
                CREATE TRIGGER fail_booking_snapshot_top
                BEFORE INSERT ON booking_baseline_snapshot_images
                WHEN NEW.angle = 'TOP'
                BEGIN
                    SELECT RAISE(ABORT, 'forced snapshot failure');
                END;
                """
            )
        )
        db.commit()

        with pytest.raises(IntegrityError, match="forced snapshot failure"):
            create_booking_baseline_snapshot(
                db, booking_id=booking.id, actor=users["owner"]
            )

        assert db.scalar(select(BookingBaselineSnapshot)) is None
        assert db.scalar(select(BookingBaselineSnapshotImage)) is None


def test_snapshot_requires_an_approved_booking_and_authorized_actor(baseline_context):
    Session, users, resource, booking = baseline_context
    with Session() as db:
        add_all_baselines(db, resource, users["owner"])

        with pytest.raises(SnapshotAccessDeniedError):
            create_booking_baseline_snapshot(
                db, booking_id=booking.id, actor=users["student"]
            )

        stored_booking = db.get(Booking, booking.id)
        assert stored_booking is not None
        stored_booking.status = BookingStatus.PENDING
        db.commit()
        with pytest.raises(SnapshotRequiresApprovedBookingError):
            create_booking_baseline_snapshot(
                db, booking_id=booking.id, actor=users["owner"]
            )


def test_database_constraints_cover_duplicate_baselines_and_booking_angles(
    baseline_context,
):
    Session, users, resource, booking = baseline_context
    with Session() as db:
        baseline = add_baseline(db, resource, users["owner"], "FRONT")
        db.add(
            ResourceBaselineImage(
                resource_id=resource.id,
                angle="FRONT",
                original_filename="duplicate.png",
                mime_type="image/png",
                byte_size=baseline.byte_size,
                sha256=baseline.sha256,
                image_data=baseline.image_data,
                uploaded_by_id=users["owner"].id,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        constraints = {
            constraint.name
            for constraint in BookingBaselineSnapshotImage.__table__.constraints
        }
        assert "uq_booking_baseline_snapshot_images_snapshot_angle" in constraints
        assert "uq_booking_baseline_snapshot_images_booking_angle" in constraints
