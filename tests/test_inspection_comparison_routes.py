from datetime import datetime, timedelta, timezone
from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
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
from app.models.resource_image import ResourceImage
from app.models.user import User
from cv_engine.angles import REQUIRED_ANGLES


def _image_bytes() -> bytes:
    pixels = np.random.default_rng(42).integers(
        0,
        256,
        size=(320, 320, 3),
        dtype=np.uint8,
    )
    buffer = BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return buffer.getvalue()


class ComparisonContext:
    def __init__(self, client, session_factory, users, booking, actor_state):
        self.client = client
        self.session_factory = session_factory
        self.users = users
        self.booking = booking
        self.actor_state = actor_state
        self.reports = {}

    def use(self, name):
        self.actor_state["user"] = self.users[name]

    def add_stage(self, stage, angles=()):
        with self.session_factory() as db:
            report = ConditionReport(
                booking_id=self.booking.id,
                submitted_by_id=self.users["student"].id,
                report_type=stage.upper(),
                condition_description=f"{stage} inspection report",
            )
            db.add(report)
            db.flush()
            image_data = _image_bytes()
            for angle in angles:
                db.add(ConditionReportImage(
                    report_id=report.id,
                    angle=angle,
                    original_filename=f"{angle.lower()}.png",
                    mime_type="image/png",
                    byte_size=len(image_data),
                    sha256="test-hash",
                    image_data=image_data,
                    uploaded_by_id=self.users["student"].id,
                ))
            db.commit()
            db.refresh(report)
            self.reports[stage.lower()] = report

    def add_gallery_image(self):
        image_data = _image_bytes()
        with self.session_factory() as db:
            db.add(ResourceImage(
                resource_id=self.booking.resource_id,
                original_filename="gallery.png",
                mime_type="image/png",
                byte_size=len(image_data),
                image_data=image_data,
                is_primary=True,
                uploaded_by_id=self.users["owner"].id,
            ))
            db.commit()


@pytest.fixture
def comparison_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)

    with session_factory() as db:
        users = {
            "student": User(
                full_name="Comparison Student",
                email="comparison-student@example.com",
                hashed_password="unused",
                role=UserRole.STUDENT,
                is_active=True,
            ),
            "owner": User(
                full_name="Comparison Owner",
                email="comparison-owner@example.com",
                hashed_password="unused",
                role=UserRole.OWNER,
                is_active=True,
            ),
            "unrelated": User(
                full_name="Unrelated Student",
                email="comparison-unrelated@example.com",
                hashed_password="unused",
                role=UserRole.STUDENT,
                is_active=True,
            ),
            "admin": User(
                full_name="Comparison Admin",
                email="comparison-admin@example.com",
                hashed_password="unused",
                role=UserRole.ADMIN,
                is_active=True,
            ),
        }
        db.add_all(users.values())
        db.flush()
        resource = Resource(
            owner_id=users["owner"].id,
            title="Comparison Resource",
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
            purpose="Inspection comparison API test",
            status=BookingStatus.RETURNED,
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)
        for user in users.values():
            db.refresh(user)

    actor_state = {"user": users["student"]}

    def override_user():
        return actor_state["user"]

    def override_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield ComparisonContext(
            client,
            session_factory,
            users,
            booking,
            actor_state,
        )
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _url(booking_id):
    return f"/bookings/{booking_id}/inspection-comparisons"


@pytest.mark.parametrize("role", ["owner", "student", "admin"])
def test_booking_participants_and_admin_can_view(comparison_context, role):
    comparison_context.use(role)

    response = comparison_context.client.get(
        _url(comparison_context.booking.id)
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["status"] == "NOT_READY"
    assert response.json()["data"]["comparisons"]["baseline_vs_initial"]["status"] == "UNAVAILABLE"


def test_unrelated_user_cannot_view_comparisons(comparison_context):
    comparison_context.use("unrelated")

    response = comparison_context.client.get(
        _url(comparison_context.booking.id)
    )

    assert response.status_code == 403


def test_nonexistent_booking_returns_404(comparison_context):
    response = comparison_context.client.get(_url(987654))

    assert response.status_code == 404


def test_nonpositive_booking_id_is_rejected(comparison_context):
    response = comparison_context.client.get(_url(0))

    assert response.status_code == 422


def test_missing_reports_are_unavailable_with_clear_reasons(comparison_context):
    response = comparison_context.client.get(
        _url(comparison_context.booking.id)
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stages"]["initial"]["status"] == "UNAVAILABLE"
    assert data["stages"]["final"]["status"] == "UNAVAILABLE"
    assert data["comparisons"]["initial_vs_final"]["status"] == "UNAVAILABLE"
    assert "INITIAL condition report" in data["comparisons"]["initial_vs_final"]["reason"]
    assert data["comparisons"]["initial_vs_final"]["overall_similarity_score"] is None


def test_missing_final_report_is_unavailable(comparison_context):
    comparison_context.add_stage("initial")

    response = comparison_context.client.get(
        _url(comparison_context.booking.id)
    )

    comparison = response.json()["data"]["comparisons"]["initial_vs_final"]
    assert comparison["status"] == "UNAVAILABLE"
    assert "FINAL condition report" in comparison["reason"]
    assert comparison["missing_angles"]["final"] == list(REQUIRED_ANGLES)


def test_missing_initial_report_is_unavailable(comparison_context):
    comparison_context.add_stage("final")

    response = comparison_context.client.get(
        _url(comparison_context.booking.id)
    )

    comparison = response.json()["data"]["comparisons"]["initial_vs_final"]
    assert comparison["status"] == "UNAVAILABLE"
    assert "INITIAL condition report" in comparison["reason"]
    assert comparison["missing_angles"]["initial"] == list(REQUIRED_ANGLES)


def test_missing_baseline_never_uses_resource_gallery_images(comparison_context):
    comparison_context.add_stage("initial")
    comparison_context.add_stage("final")
    comparison_context.add_gallery_image()

    response = comparison_context.client.get(
        _url(comparison_context.booking.id)
    )

    data = response.json()["data"]
    assert data["stages"]["baseline"]["status"] == "UNAVAILABLE"
    assert data["stages"]["baseline"]["present_angles"] == []
    assert data["comparisons"]["baseline_vs_initial"]["status"] == "UNAVAILABLE"
    assert data["comparisons"]["baseline_vs_final"]["status"] == "UNAVAILABLE"
    assert data["status"] == "NOT_READY"
    assert data["stages"]["baseline"]["present_angles"] == []


def test_incomplete_angles_are_reported_without_claiming_completion(comparison_context):
    comparison_context.add_stage("initial", ["FRONT"])
    comparison_context.add_stage("final", ["FRONT"])

    response = comparison_context.client.get(
        _url(comparison_context.booking.id)
    )

    data = response.json()["data"]
    comparison = data["comparisons"]["initial_vs_final"]
    assert response.status_code == 200
    assert comparison["status"] == "PARTIAL"
    assert comparison["completed_angles"] < 6
    assert comparison["missing_angles"]["initial"] == [
        angle for angle in REQUIRED_ANGLES if angle != "FRONT"
    ]
    assert comparison["angles"]["BACK"]["status"] == "MISSING"
    assert data["status"] == "NOT_READY"


def test_successful_initial_final_comparison_returns_no_image_bytes(comparison_context):
    comparison_context.add_stage("initial", REQUIRED_ANGLES)
    comparison_context.add_stage("final", REQUIRED_ANGLES)

    response = comparison_context.client.get(
        _url(comparison_context.booking.id)
    )

    assert response.status_code == 200
    assert "image_data" not in response.text
    assert "original_filename" not in response.text
    data = response.json()["data"]
    initial_final = data["comparisons"]["initial_vs_final"]
    assert initial_final["status"] == "COMPLETED"
    assert initial_final["completed_angles"] == 6
    assert initial_final["failed_angles"] == []
    assert initial_final["angles"]["FRONT"]["similarity_score"] is not None
    assert initial_final["manual_review_required"] is True
    assert data["comparisons"]["baseline_vs_initial"]["status"] == "UNAVAILABLE"


def test_cv_engine_failure_returns_internal_server_error(
    comparison_context,
    monkeypatch,
):
    comparison_context.add_stage("initial")
    comparison_context.add_stage("final")

    def fail_comparison(*args):
        raise RuntimeError("engine failed")

    monkeypatch.setattr(
        "app.services.inspection_comparison_api_service.compare_inspection_stages",
        fail_comparison,
    )

    response = comparison_context.client.get(
        _url(comparison_context.booking.id)
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Inspection comparison could not be completed."
