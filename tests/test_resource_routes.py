
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.user import User
from app.models.enums import UserRole
from app.core.security import hash_password, create_access_token


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

    with TestClient(app) as test_client:
        yield test_client, TestingSession

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
            email="admin@example.com",
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


def resource_payload(title="Projector"):
    return {
        "title": title,
        "description": "Campus projector",
        "category": "Electronics",
        "resource_type": "EQUIPMENT",
        "location": "Block A",
        "usage_rules": "Handle with care",
    }


def create_resource(client, headers, title="Projector"):
    return client.post(
        "/resources",
        json=resource_payload(title),
        headers=headers,
    )


def test_owner_can_create_resource_and_owner_id_is_derived(test_context):
    client, _ = test_context

    owner_headers = register_user(
        client, "Owner One", "owner1@example.com", "OWNER"
    )

    response = create_resource(client, owner_headers)

    assert response.status_code == 201
    assert response.json()["owner_id"] > 0
    assert response.json()["title"] == "Projector"


def test_student_cannot_create_resource(test_context):
    client, _ = test_context

    student_headers = register_user(
        client, "Student One", "student@example.com", "STUDENT"
    )

    response = create_resource(client, student_headers)

    assert response.status_code == 403


def test_owner_can_update_own_resource(test_context):
    client, _ = test_context

    owner_headers = register_user(
        client, "Owner One", "owner1@example.com", "OWNER"
    )

    created = create_resource(client, owner_headers)
    resource_id = created.json()["id"]

    response = client.patch(
        f"/resources/{resource_id}",
        json={"title": "Updated Projector"},
        headers=owner_headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Projector"


def test_owner_cannot_update_another_owners_resource(test_context):
    client, _ = test_context

    owner_a_headers = register_user(
        client, "Owner A", "ownera@example.com", "OWNER"
    )

    owner_b_headers = register_user(
        client, "Owner B", "ownerb@example.com", "OWNER"
    )

    created = create_resource(client, owner_a_headers)
    resource_id = created.json()["id"]

    response = client.patch(
        f"/resources/{resource_id}",
        json={"title": "Unauthorized Update"},
        headers=owner_b_headers,
    )

    assert response.status_code == 403


def test_admin_can_update_any_resource(test_context):
    client, TestingSession = test_context

    owner_headers = register_user(
        client, "Owner One", "owner1@example.com", "OWNER"
    )

    admin_headers = create_admin(TestingSession)

    created = create_resource(client, owner_headers)
    resource_id = created.json()["id"]

    response = client.patch(
        f"/resources/{resource_id}",
        json={"title": "Admin Updated Resource"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Admin Updated Resource"


def test_student_cannot_update_resource(test_context):
    client, _ = test_context

    owner_headers = register_user(
        client, "Owner One", "owner1@example.com", "OWNER"
    )

    student_headers = register_user(
        client, "Student One", "student@example.com", "STUDENT"
    )

    created = create_resource(client, owner_headers)
    resource_id = created.json()["id"]

    response = client.patch(
        f"/resources/{resource_id}",
        json={"title": "Unauthorized Update"},
        headers=student_headers,
    )

    assert response.status_code == 403


def test_public_list_shows_only_active_resources(test_context):
    client, _ = test_context

    owner_headers = register_user(
        client, "Owner One", "owner1@example.com", "OWNER"
    )

    active = create_resource(client, owner_headers, "Active Projector")
    inactive = create_resource(client, owner_headers, "Inactive Projector")

    inactive_id = inactive.json()["id"]

    client.patch(
        f"/resources/{inactive_id}",
        json={"is_active": False},
        headers=owner_headers,
    )

    response = client.get("/resources")

    assert response.status_code == 200

    titles = [item["title"] for item in response.json()]

    assert "Active Projector" in titles
    assert "Inactive Projector" not in titles


def test_public_detail_hides_inactive_resource(test_context):
    client, _ = test_context

    owner_headers = register_user(
        client, "Owner One", "owner1@example.com", "OWNER"
    )

    created = create_resource(client, owner_headers)
    resource_id = created.json()["id"]

    client.patch(
        f"/resources/{resource_id}",
        json={"is_active": False},
        headers=owner_headers,
    )

    response = client.get(f"/resources/{resource_id}")

    assert response.status_code == 404


def test_resource_creation_rejects_invalid_availability(test_context):
    client, _ = test_context

    owner_headers = register_user(
        client, "Owner One", "owner1@example.com", "OWNER"
    )

    payload = resource_payload()
    payload["available_from"] = "2026-11-02T12:00:00"
    payload["available_until"] = "2026-11-02T10:00:00"

    response = client.post(
        "/resources",
        json=payload,
        headers=owner_headers,
    )

    assert response.status_code == 422


def test_resource_update_rejects_invalid_merged_availability(test_context):
    client, _ = test_context

    owner_headers = register_user(
        client, "Owner One", "owner1@example.com", "OWNER"
    )

    payload = resource_payload()
    payload["available_from"] = "2026-11-02T10:00:00"
    payload["available_until"] = "2026-11-02T12:00:00"

    created = client.post(
        "/resources",
        json=payload,
        headers=owner_headers,
    )

    resource_id = created.json()["id"]

    response = client.patch(
        f"/resources/{resource_id}",
        json={"available_until": "2026-11-02T09:00:00"},
        headers=owner_headers,
    )

    assert response.status_code == 422