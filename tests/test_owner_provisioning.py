import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.enums import UserRole
from app.models.user import User
from scripts import provision_account as provisioning


@pytest.fixture
def test_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, testing_session

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_provisioned_owner_can_authenticate_and_manage_owned_resources(
    test_context,
):
    client, testing_session = test_context
    with testing_session() as db:
        owner = provisioning.provision_account(
            db,
            full_name="Resource Owner",
            email="OWNER@example.com",
            password="SecureOwnerPass123",
            role=UserRole.OWNER,
            institution="OpenBench Campus",
        )
        owner_id = owner.id
        assert owner.email == "owner@example.com"
        assert owner.hashed_password != "SecureOwnerPass123"

    invalid_login = client.post(
        "/auth/login",
        json={
            "email": "owner@example.com",
            "password": "WrongPassword123",
        },
    )
    assert invalid_login.status_code == 401

    login = client.post(
        "/auth/login",
        json={
            "email": "owner@example.com",
            "password": "SecureOwnerPass123",
        },
    )
    assert login.status_code == 200
    assert login.json()["data"]["user"]["role"] == "OWNER"
    headers = {
        "Authorization": f"Bearer {login.json()['data']['access_token']}"
    }

    current_user = client.get("/auth/me", headers=headers)
    assert current_user.status_code == 200
    assert current_user.json()["data"]["role"] == "OWNER"

    resource = client.post(
        "/resources",
        headers=headers,
        json={
            "title": "Owner Projector",
            "description": "Classroom projector",
            "category": "Electronics",
            "resource_type": "EQUIPMENT",
            "location": "Building A",
            "usage_rules": "Handle carefully",
        },
    )
    assert resource.status_code == 201
    assert resource.json()["owner_id"] == owner_id

    update = client.patch(
        f"/resources/{resource.json()['id']}",
        headers=headers,
        json={"title": "Updated Projector"},
    )
    assert update.status_code == 200
    assert update.json()["title"] == "Updated Projector"


def test_duplicate_owner_email_is_rejected_without_second_account(
    test_context,
):
    _, testing_session = test_context
    with testing_session() as db:
        provisioning.provision_account(
            db,
            full_name="First Owner",
            email="same-owner@example.com",
            password="SecureOwnerPass123",
            role=UserRole.OWNER,
        )

    with testing_session() as db:
        with pytest.raises(ValueError, match="already exists"):
            provisioning.provision_account(
                db,
                full_name="Second Owner",
                email="SAME-OWNER@example.com",
                password="AnotherSecurePass123",
                role=UserRole.OWNER,
            )
        assert db.query(User).filter_by(email="same-owner@example.com").count() == 1


def test_owner_cannot_register_publicly_or_access_admin_operations(
    test_context,
):
    client, testing_session = test_context
    public_owner_registration = client.post(
        "/auth/register",
        json={
            "full_name": "Public Owner",
            "email": "public-owner@example.com",
            "password": "SecureOwnerPass123",
            "role": "OWNER",
        },
    )
    assert public_owner_registration.status_code == 422

    with testing_session() as db:
        owner = provisioning.provision_account(
            db,
            full_name="Restricted Owner",
            email="restricted-owner@example.com",
            password="SecureOwnerPass123",
            role=UserRole.OWNER,
        )
        headers = {
            "Authorization": f"Bearer {create_access_token(owner.id)}"
        }

    admin_operation = client.patch(
        "/qualifications/1/verify",
        headers=headers,
        json={"status": "VERIFIED"},
    )
    assert admin_operation.status_code == 403


def test_cli_uses_hidden_password_prompt_and_does_not_print_password(
    monkeypatch, capsys, test_context
):
    _, testing_session = test_context
    monkeypatch.setattr(provisioning, "SessionLocal", testing_session)
    monkeypatch.setattr(
        "sys.argv",
        ["provision_account", "OWNER"],
    )
    prompts = iter(
        [
            "CLI Owner",
            "cli-owner@example.com",
            "Example Campus",
        ]
    )
    passwords = iter(
        [
            "SecureOwnerPass123",
            "SecureOwnerPass123",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: next(prompts))
    monkeypatch.setattr(
        provisioning,
        "getpass",
        lambda _prompt: next(passwords),
    )

    provisioning.main()

    output = capsys.readouterr().out
    assert "Provisioned OWNER account" in output
    assert "SecureOwnerPass123" not in output


def test_student_registration_stays_public_and_cannot_create_resources(
    test_context,
):
    client, _ = test_context
    registration = client.post(
        "/auth/register",
        json={
            "full_name": "Campus Student",
            "email": "student@example.com",
            "password": "SecureStudentPass123",
        },
    )
    assert registration.status_code == 201
    assert registration.json()["data"]["user"]["role"] == "STUDENT"

    duplicate = client.post(
        "/auth/register",
        json={
            "full_name": "Duplicate Student",
            "email": "STUDENT@example.com",
            "password": "SecureStudentPass123",
        },
    )
    assert duplicate.status_code == 409

    headers = {
        "Authorization": (
            f"Bearer {registration.json()['data']['access_token']}"
        )
    }
    resource = client.post(
        "/resources",
        headers=headers,
        json={
            "title": "Unauthorized Projector",
            "category": "Electronics",
            "resource_type": "EQUIPMENT",
            "location": "Building B",
        },
    )
    assert resource.status_code == 403
