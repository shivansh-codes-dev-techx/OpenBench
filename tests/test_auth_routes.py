import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db


@pytest.fixture
def client():
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
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def register_student(client):
    return client.post(
        "/auth/register",
        json={
            "full_name": "Test Student",
            "email": "student@example.com",
            "password": "StrongPass123",
            "role": "STUDENT",
        },
    )


def test_registration_success(client):
    response = register_student(client)

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["data"]["access_token"]
    assert body["data"]["token_type"] == "bearer"
    assert body["data"]["user"]["role"] == "STUDENT"
    assert "hashed_password" not in body["data"]["user"]


def test_duplicate_registration(client):
    register_student(client)

    response = register_student(client)

    assert response.status_code == 409


def test_admin_registration_blocked(client):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "StrongPass123",
            "role": "ADMIN",
        },
    )

    assert response.status_code == 422


def test_login_success(client):
    register_student(client)

    response = client.post(
        "/auth/login",
        json={
            "email": "student@example.com",
            "password": "StrongPass123",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["access_token"]


def test_login_invalid_password(client):
    register_student(client)

    response = client.post(
        "/auth/login",
        json={
            "email": "student@example.com",
            "password": "WrongPassword123",
        },
    )

    assert response.status_code == 401


def test_me_without_token(client):
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_me_with_valid_token(client):
    registration = register_student(client)
    token = registration.json()["data"]["access_token"]

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["email"] == "student@example.com"


def test_me_with_invalid_token(client):
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )

    assert response.status_code == 401