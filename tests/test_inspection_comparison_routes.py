from datetime import datetime, timedelta, timezone
from io import BytesIO
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import cv2
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
from app.services.inspection_comparison_api_service import (
    get_booking_inspection_comparisons,
)
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


def _install_complete_angle_engine(monkeypatch):
    def inspect_all_angles(reference_images, target_images):
        angles = {}
        failed_angles = []
        for angle in REQUIRED_ANGLES:
            if angle not in reference_images or angle not in target_images:
                failed_angles.append(angle)
                angles[angle] = {
                    "angle": angle,
                    "status": "MISSING",
                    "similarity_score": None,
                    "difference_percentage": None,
                    "potential_regions": [],
                    "review_required": True,
                    "attention_required": True,
                    "manual_review_required": True,
                    "message": "An image is missing.",
                    "quality_warnings": [],
                    "alignment_warnings": [],
                }
            else:
                angles[angle] = {
                    "angle": angle,
                    "status": "COMPLETED",
                    "similarity_score": 98.5,
                    "difference_percentage": 0.5,
                    "potential_regions": [],
                    "review_required": False,
                    "attention_required": False,
                    "manual_review_required": True,
                    "message": "Comparison completed.",
                    "quality_warnings": [],
                    "alignment_warnings": [],
                }

        completed = len(REQUIRED_ANGLES) - len(failed_angles)
        score_status = (
            "UNAVAILABLE" if completed == 0
            else "PARTIAL" if completed < len(REQUIRED_ANGLES)
            else "COMPLETE"
        )
        result = {
            "status": "COMPLETED" if not failed_angles else "PARTIAL",
            "total_angles": len(REQUIRED_ANGLES),
            "completed_angles": completed,
            "failed_angles": failed_angles,
            "missing_angles": failed_angles,
            "angles": angles,
            "overall_similarity_score": 98.5 if completed else None,
            "overall_score_status": score_status,
            "overall_status": score_status,
            "review_required": bool(failed_angles),
            "attention_required": bool(failed_angles),
            "manual_review_required": True,
        }
        return SimpleNamespace(to_dict=lambda: result)

    monkeypatch.setattr(
        "app.services.inspection_comparison_service.inspect_all_angles",
        inspect_all_angles,
    )


def _install_baseline_storage_contract(monkeypatch, baseline_images):
    snapshot = object()
    image_rows = [object() for _ in REQUIRED_ANGLES]
    reader = Mock(return_value=(snapshot, image_rows))
    converter = Mock(return_value=baseline_images)

    storage_module = ModuleType(
        "app.services.booking_baseline_snapshot_service"
    )
    storage_module.get_booking_baseline_snapshot_images = reader
    adapter_module = ModuleType("app.services.baseline_snapshot_adapter")
    adapter_module.snapshot_records_to_angle_bytes = converter
    monkeypatch.setitem(
        sys.modules,
        "app.services.booking_baseline_snapshot_service",
        storage_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "app.services.baseline_snapshot_adapter",
        adapter_module,
    )
    return reader, converter, image_rows


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
    for comparison_name in ("baseline_vs_initial", "baseline_vs_final"):
        comparison = data["comparisons"][comparison_name]
        assert comparison["overall_status"] == "UNAVAILABLE"
        assert comparison["manual_review_required"] is True
        assert all(
            comparison["angles"][angle]["alignment_warnings"] == []
            for angle in REQUIRED_ANGLES
        )
    assert data["status"] == "NOT_READY"
    assert data["stages"]["baseline"]["present_angles"] == []


def test_mock_baseline_provider_runs_all_three_comparisons(
    comparison_context,
    monkeypatch,
):
    comparison_context.add_stage("initial", REQUIRED_ANGLES)
    comparison_context.add_stage("final", REQUIRED_ANGLES)
    _install_complete_angle_engine(monkeypatch)
    baseline = {angle: _image_bytes() for angle in REQUIRED_ANGLES}
    provider = Mock(return_value=baseline)

    with comparison_context.session_factory() as db:
        result = get_booking_inspection_comparisons(
            db,
            comparison_context.booking.id,
            comparison_context.users["student"],
            baseline_provider=provider,
        )
        provider.assert_called_once_with(
            db,
            comparison_context.booking.id,
            comparison_context.users["student"],
        )

    assert result["stages"]["baseline"]["status"] == "AVAILABLE"
    assert result["stages"]["baseline"]["present_angles"] == list(REQUIRED_ANGLES)
    assert set(result["comparisons"]) == {
        "baseline_vs_initial",
        "initial_vs_final",
        "baseline_vs_final",
    }
    for comparison in result["comparisons"].values():
        assert comparison["overall_status"] == "COMPLETE"
        assert comparison["completed_angles"] == 6
        assert comparison["failed_angles"] == []
        assert comparison["manual_review_required"] is True
    assert result["status"] == "COMPLETED"


def test_storage_service_and_adapter_receive_authenticated_actor(
    comparison_context,
    monkeypatch,
):
    comparison_context.add_stage("initial", REQUIRED_ANGLES)
    comparison_context.add_stage("final", REQUIRED_ANGLES)
    _install_complete_angle_engine(monkeypatch)
    baseline = {angle: _image_bytes() for angle in REQUIRED_ANGLES}
    reader, converter, image_rows = _install_baseline_storage_contract(
        monkeypatch,
        baseline,
    )

    with comparison_context.session_factory() as db:
        result = get_booking_inspection_comparisons(
            db,
            comparison_context.booking.id,
            comparison_context.users["student"],
        )
        reader.assert_called_once_with(
            db,
            booking_id=comparison_context.booking.id,
            actor=comparison_context.users["student"],
        )
        converter.assert_called_once_with(image_rows)

    assert all(
        result["comparisons"][name]["overall_status"] == "COMPLETE"
        for name in (
            "baseline_vs_initial",
            "initial_vs_final",
            "baseline_vs_final",
        )
    )


def test_incomplete_baseline_is_partial_and_preserves_initial_final(
    comparison_context,
    monkeypatch,
):
    comparison_context.add_stage("initial", REQUIRED_ANGLES)
    comparison_context.add_stage("final", REQUIRED_ANGLES)
    _install_complete_angle_engine(monkeypatch)
    provider = Mock(return_value={"FRONT": _image_bytes()})

    with comparison_context.session_factory() as db:
        result = get_booking_inspection_comparisons(
            db,
            comparison_context.booking.id,
            comparison_context.users["student"],
            baseline_provider=provider,
        )

    baseline_initial = result["comparisons"]["baseline_vs_initial"]
    assert baseline_initial["overall_status"] == "PARTIAL"
    assert baseline_initial["completed_angles"] == 1
    assert baseline_initial["missing_angles"]["baseline"] == [
        angle for angle in REQUIRED_ANGLES if angle != "FRONT"
    ]
    assert result["comparisons"]["initial_vs_final"]["overall_status"] == "COMPLETE"
    assert result["manual_review_required"] is True


def test_corrupt_baseline_image_is_a_failed_angle_not_an_api_error(
    comparison_context,
    monkeypatch,
):
    comparison_context.add_stage("initial", REQUIRED_ANGLES)
    comparison_context.add_stage("final", REQUIRED_ANGLES)
    _install_complete_angle_engine(monkeypatch)
    baseline = {angle: _image_bytes() for angle in REQUIRED_ANGLES}
    baseline["FRONT"] = b"corrupt baseline bytes"
    provider = Mock(return_value=baseline)

    with comparison_context.session_factory() as db:
        result = get_booking_inspection_comparisons(
            db,
            comparison_context.booking.id,
            comparison_context.users["student"],
            baseline_provider=provider,
        )

    baseline_initial = result["comparisons"]["baseline_vs_initial"]
    assert baseline_initial["overall_status"] == "PARTIAL"
    assert baseline_initial["angles"]["FRONT"]["status"] == "FAILED"
    assert baseline_initial["angles"]["FRONT"]["similarity_score"] is None
    assert "baseline:" in baseline_initial["angles"]["FRONT"]["message"]
    assert "FRONT" in baseline_initial["failed_angles"]
    assert result["comparisons"]["initial_vs_final"]["overall_status"] == "COMPLETE"


def test_baseline_provider_failure_keeps_other_pair_available(
    comparison_context,
    monkeypatch,
):
    comparison_context.add_stage("initial", REQUIRED_ANGLES)
    comparison_context.add_stage("final", REQUIRED_ANGLES)
    _install_complete_angle_engine(monkeypatch)
    provider = Mock(side_effect=RuntimeError("storage unavailable"))

    with comparison_context.session_factory() as db:
        result = get_booking_inspection_comparisons(
            db,
            comparison_context.booking.id,
            comparison_context.users["student"],
            baseline_provider=provider,
        )

    assert result["stages"]["baseline"]["status"] == "UNAVAILABLE"
    assert result["comparisons"]["baseline_vs_initial"]["overall_status"] == "UNAVAILABLE"
    assert result["comparisons"]["baseline_vs_final"]["overall_status"] == "UNAVAILABLE"
    assert result["comparisons"]["initial_vs_final"]["overall_status"] == "COMPLETE"
    assert result["manual_review_required"] is True


def test_malformed_baseline_provider_result_is_unavailable(
    comparison_context,
    monkeypatch,
):
    comparison_context.add_stage("initial", REQUIRED_ANGLES)
    comparison_context.add_stage("final", REQUIRED_ANGLES)
    _install_complete_angle_engine(monkeypatch)
    provider = Mock(return_value=["not", "an", "angle mapping"])

    with comparison_context.session_factory() as db:
        result = get_booking_inspection_comparisons(
            db,
            comparison_context.booking.id,
            comparison_context.users["student"],
            baseline_provider=provider,
        )

    assert result["stages"]["baseline"]["status"] == "UNAVAILABLE"
    assert "invalid image mapping" in result["stages"]["baseline"]["reason"]
    assert result["comparisons"]["baseline_vs_initial"]["overall_status"] == "UNAVAILABLE"
    assert result["comparisons"]["initial_vs_final"]["overall_status"] == "COMPLETE"


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
    assert comparison["overall_status"] == "PARTIAL"
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
    assert initial_final["overall_status"] == "COMPLETE"
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


@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: ValueError("private validation path detail"),
        lambda: cv2.error("private OpenCV implementation detail"),
    ],
    ids=["value-error", "opencv-error"],
)
def test_processing_exception_details_are_logged_but_redacted_from_api(
    comparison_context,
    monkeypatch,
    caplog,
    error_factory,
):
    comparison_context.add_stage("initial", REQUIRED_ANGLES)
    comparison_context.add_stage("final", REQUIRED_ANGLES)

    def fail_angle(*args, **kwargs):
        raise error_factory()

    monkeypatch.setattr("cv_engine.inspection.inspect_angle", fail_angle)
    response = comparison_context.client.get(
        _url(comparison_context.booking.id)
    )

    assert response.status_code == 200
    assert "private" not in response.text
    assert "private" in caplog.text
    data = response.json()["data"]
    comparison = data["comparisons"]["initial_vs_final"]
    assert comparison["angles"]["FRONT"]["message"] == (
        "Image comparison could not be processed."
    )
    assert comparison["angles"]["FRONT"]["status"] == "FAILED"
    assert comparison["manual_review_required"] is True
