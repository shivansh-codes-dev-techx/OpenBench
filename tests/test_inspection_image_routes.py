from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.booking import Booking
from app.models.condition_report import ConditionReport
from app.models.condition_report_image import ConditionReportImage
from app.models.enums import BookingStatus, ResourceType, UserRole
from app.models.resource import Resource
from app.models.user import User
from app.services.inspection_image_service import (
    load_booking_inspection_images,
)


def make_image_bytes(image_format="PNG") -> bytes:
    image = Image.new("RGB", (320, 320), (80, 120, 160))
    buffer = BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()


def make_png_bytes() -> bytes:
    return make_image_bytes("PNG")


class ImageTestContext:
    def __init__(self, client, session_factory, users, reports, bookings, actor_state):
        self.client = client
        self.session_factory = session_factory
        self.users = users
        self.reports = reports
        self.bookings = bookings
        self.actor_state = actor_state

    def use(self, username: str) -> None:
        self.actor_state["user"] = self.users[username]


@pytest.fixture
def image_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )
    Base.metadata.create_all(bind=engine)

    with session_factory() as db:
        users = {
            "student": User(
                full_name="Image Student",
                email="image-student@example.com",
                hashed_password="unused",
                role=UserRole.STUDENT,
                is_active=True,
            ),
            "owner": User(
                full_name="Image Owner",
                email="image-owner@example.com",
                hashed_password="unused",
                role=UserRole.OWNER,
                is_active=True,
            ),
            "unrelated": User(
                full_name="Unrelated User",
                email="image-unrelated@example.com",
                hashed_password="unused",
                role=UserRole.STUDENT,
                is_active=True,
            ),
        }
        db.add_all(users.values())
        db.flush()

        resource = Resource(
            owner_id=users["owner"].id,
            title="Inspection Camera",
            description="Test resource",
            category="equipment",
            resource_type=ResourceType.EQUIPMENT,
            location="Lab",
            is_active=True,
        )
        db.add(resource)
        db.flush()

        now = datetime.now(timezone.utc)
        bookings = {
            "initial": Booking(
                student_id=users["student"].id,
                resource_id=resource.id,
                start_at=now,
                end_at=now + timedelta(hours=1),
                purpose="Inspection image API test",
                status=BookingStatus.APPROVED,
            ),
            "final": Booking(
                student_id=users["student"].id,
                resource_id=resource.id,
                start_at=now,
                end_at=now + timedelta(hours=1),
                purpose="Inspection image API test",
                status=BookingStatus.IN_USE,
            ),
        }
        db.add_all(bookings.values())
        db.flush()
        reports = {
            "initial": ConditionReport(
                booking_id=bookings["initial"].id,
                submitted_by_id=users["student"].id,
                report_type="INITIAL",
                condition_description="Initial condition for image tests",
            ),
            "final": ConditionReport(
                booking_id=bookings["final"].id,
                submitted_by_id=users["student"].id,
                report_type="FINAL",
                condition_description="Final condition for image tests",
            ),
        }
        db.add_all(reports.values())
        db.commit()
        for item in (*users.values(), *bookings.values(), *reports.values()):
            db.refresh(item)

    actor_state = {"user": users["student"]}

    def override_user():
        return actor_state["user"]

    def override_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield ImageTestContext(client, session_factory, users, reports, bookings, actor_state)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def upload(context, *, stage="initial", angle="FRONT", image_data=None, mime_type="image/png"):
    booking = context.bookings[stage]
    report = context.reports[stage]
    return context.client.post(
        f"/bookings/{booking.id}/condition-reports/{report.id}/images",
        files={"file": ("evidence.png", image_data or make_png_bytes(), mime_type)},
        data={"angle": angle},
    )


def test_uploads_all_six_initial_angles_and_returns_approved_metadata(image_context):
    expected_angles = {"FRONT", "BACK", "LEFT", "RIGHT", "TOP", "BOTTOM"}
    returned = []
    for angle in expected_angles:
        response = upload(image_context, angle=angle.lower())
        assert response.status_code == 201
        item = response.json()
        assert item["booking_id"] == image_context.bookings["initial"].id
        assert item["report_id"] == image_context.reports["initial"].id
        assert item["stage"] == "INITIAL"
        assert item["angle"] == angle
        assert item["mime_type"] == "image/png"
        assert item["byte_size"] == len(make_png_bytes())
        assert item["sha256"] == hashlib.sha256(make_png_bytes()).hexdigest()
        assert item["uploaded_at"]
        returned.append(item)
    assert len({item["image_id"] for item in returned}) == 6


def test_final_stage_is_derived_from_existing_report(image_context):
    response = upload(image_context, stage="final", angle="TOP")
    assert response.status_code == 201
    assert response.json()["stage"] == "FINAL"
    assert response.json()["booking_id"] == image_context.bookings["final"].id


@pytest.mark.parametrize(
    ("image_format", "mime_type"),
    [("JPEG", "image/jpeg"), ("WEBP", "image/webp")],
)
def test_jpeg_and_webp_are_accepted(image_context, image_format, mime_type):
    response = upload(
        image_context,
        angle="BACK",
        image_data=make_image_bytes(image_format),
        mime_type=mime_type,
    )
    assert response.status_code == 201
    assert response.json()["mime_type"] == mime_type


def test_duplicate_angle_returns_409_and_keeps_original_bytes(image_context):
    first = upload(image_context)
    second = upload(image_context, image_data=make_png_bytes() + b"extra")
    assert first.status_code == 201
    assert second.status_code == 409
    with image_context.session_factory() as db:
        rows = list(db.scalars(select(ConditionReportImage)).all())
        assert len(rows) == 1
        assert rows[0].image_data == make_png_bytes()


@pytest.mark.parametrize("angle", ["DIAGONAL", "", "FRONT/../BACK"])
def test_invalid_angles_are_rejected(image_context, angle):
    response = upload(image_context, angle=angle)
    assert response.status_code == 422


def test_invalid_or_corrupt_content_is_rejected(image_context):
    corrupt = upload(image_context, image_data=b"not an image")
    mime_mismatch = upload(image_context, angle="BACK", mime_type="image/jpeg")
    assert corrupt.status_code == 422
    assert mime_mismatch.status_code == 415


def test_oversized_file_is_rejected_before_decode(image_context):
    from cv_engine.quality import MAX_IMAGE_BYTES

    response = upload(image_context, image_data=b"x" * (MAX_IMAGE_BYTES + 1))
    assert response.status_code == 413


def test_unrelated_user_cannot_upload_list_or_retrieve(image_context):
    uploaded = upload(image_context)
    image_id = uploaded.json()["image_id"]
    image_context.use("unrelated")
    booking = image_context.bookings["initial"]
    report = image_context.reports["initial"]
    base = f"/bookings/{booking.id}/condition-reports/{report.id}/images"
    assert upload(image_context, angle="BACK").status_code == 403
    assert image_context.client.get(base).status_code == 403
    assert image_context.client.get(f"{base}/{image_id}").status_code == 403


def test_owner_and_admin_can_retrieve_images(image_context):
    uploaded = upload(image_context)
    image_id = uploaded.json()["image_id"]
    booking = image_context.bookings["initial"]
    report = image_context.reports["initial"]
    url = f"/bookings/{booking.id}/condition-reports/{report.id}/images/{image_id}"
    image_context.use("owner")
    assert image_context.client.get(url).status_code == 200
    image_context.users["admin"] = SimpleNamespace(id=100, role=UserRole.ADMIN)
    image_context.use("admin")
    assert image_context.client.get(url).status_code == 200


def test_list_response_contains_metadata_and_no_storage_details(image_context):
    upload(image_context)
    booking = image_context.bookings["initial"]
    report = image_context.reports["initial"]
    response = image_context.client.get(
        f"/bookings/{booking.id}/condition-reports/{report.id}/images"
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["images"]) == 1
    assert set(body["images"][0]) == {
        "image_id", "booking_id", "report_id", "angle", "stage",
        "mime_type", "byte_size", "sha256", "uploaded_at",
    }
    assert "image_data" not in response.text
    assert "original_filename" not in response.text


def test_retrieval_returns_original_bytes_and_content_type(image_context):
    image_bytes = make_png_bytes()
    uploaded = upload(image_context, image_data=image_bytes)
    image_id = uploaded.json()["image_id"]
    booking = image_context.bookings["initial"]
    report = image_context.reports["initial"]
    response = image_context.client.get(
        f"/bookings/{booking.id}/condition-reports/{report.id}/images/{image_id}"
    )
    assert response.status_code == 200
    assert response.content == image_bytes
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"


def test_missing_images_and_mismatched_report_ids(image_context):
    initial_booking = image_context.bookings["initial"]
    initial_report = image_context.reports["initial"]
    final_report = image_context.reports["final"]
    base = f"/bookings/{initial_booking.id}/condition-reports/{initial_report.id}/images"
    assert image_context.client.get(base).json() == {"images": []}
    assert image_context.client.get(f"{base}/987654").status_code == 404
    assert image_context.client.get(
        f"/bookings/{initial_booking.id}/condition-reports/{final_report.id}/images"
    ).status_code == 404


def test_cv_loader_returns_bytes_by_angle_and_omits_missing_angles(image_context):
    front = upload(image_context, angle="FRONT")
    assert front.status_code == 201
    with image_context.session_factory() as db:
        final_report = ConditionReport(
            booking_id=image_context.bookings["initial"].id,
            submitted_by_id=image_context.users["student"].id,
            report_type="FINAL",
            condition_description="Selected FINAL report for CV loader test",
        )
        db.add(final_report)
        db.flush()
        final_image_bytes = make_png_bytes()
        db.add(ConditionReportImage(
            report_id=final_report.id,
            angle="BOTTOM",
            original_filename="final.png",
            mime_type="image/png",
            byte_size=len(final_image_bytes),
            sha256=hashlib.sha256(final_image_bytes).hexdigest(),
            image_data=final_image_bytes,
            uploaded_by_id=image_context.users["student"].id,
        ))
        db.commit()
        initial, final = load_booking_inspection_images(
            db,
            image_context.bookings["initial"].id,
            image_context.reports["initial"].id,
            final_report.id,
        )
    assert set(initial) == {"FRONT"}
    assert isinstance(initial["FRONT"], bytes)
    assert set(final) == {"BOTTOM"}
    assert isinstance(final["BOTTOM"], bytes)


def test_cv_loader_rejects_nonexistent_report_ids(image_context):
    with image_context.session_factory() as db:
        with pytest.raises(LookupError, match="INITIAL condition report 987654"):
            load_booking_inspection_images(
                db,
                image_context.bookings["initial"].id,
                987654,
                image_context.reports["final"].id,
            )


def test_cv_loader_rejects_cross_booking_report_ids(image_context):
    with image_context.session_factory() as db:
        with pytest.raises(LookupError, match="FINAL condition report"):
            load_booking_inspection_images(
                db,
                image_context.bookings["initial"].id,
                image_context.reports["initial"].id,
                image_context.reports["final"].id,
            )


def test_cv_loader_rejects_reports_with_incorrect_stage(image_context):
    with image_context.session_factory() as db:
        same_booking_final = ConditionReport(
            booking_id=image_context.bookings["initial"].id,
            submitted_by_id=image_context.users["student"].id,
            report_type="FINAL",
            condition_description="FINAL report for wrong-stage test",
        )
        db.add(same_booking_final)
        db.commit()
        with pytest.raises(ValueError, match="expected INITIAL"):
            load_booking_inspection_images(
                db,
                image_context.bookings["initial"].id,
                same_booking_final.id,
                image_context.reports["final"].id,
            )

        with pytest.raises(ValueError, match="expected FINAL"):
            load_booking_inspection_images(
                db,
                image_context.bookings["initial"].id,
                image_context.reports["initial"].id,
                image_context.reports["initial"].id,
            )
