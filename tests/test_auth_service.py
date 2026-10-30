import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.user import UserRegister
from app.services.auth_service import (
    register_user,
    authenticate_user,
)


@pytest.fixture
def db():
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

    session = TestingSession()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_register_student(db):
    user_data = UserRegister(
        full_name="Test Student",
        email="student@example.com",
        password="StrongPass123",
    )

    user = register_user(db, user_data)

    assert user.id is not None
    assert user.role == UserRole.STUDENT
    assert user.email == "student@example.com"
    assert user.hashed_password != "StrongPass123"


def test_register_owner(db):
    user_data = UserRegister(
        full_name="Test Owner",
        email="owner@example.com",
        password="StrongPass123",
        role=UserRole.OWNER,
    )

    user = register_user(db, user_data)

    assert user.role == UserRole.OWNER


def test_duplicate_email_rejected(db):
    user_data = UserRegister(
        full_name="First User",
        email="same@example.com",
        password="StrongPass123",
    )

    register_user(db, user_data)

    duplicate = UserRegister(
        full_name="Second User",
        email="same@example.com",
        password="StrongPass123",
    )

    with pytest.raises(ValueError, match="Email already registered"):
        register_user(db, duplicate)


def test_successful_login(db):
    user_data = UserRegister(
        full_name="Test Student",
        email="student@example.com",
        password="StrongPass123",
    )

    register_user(db, user_data)

    user = authenticate_user(
        db,
        "student@example.com",
        "StrongPass123",
    )

    assert user is not None
    assert user.email == "student@example.com"


def test_wrong_password_rejected(db):
    user_data = UserRegister(
        full_name="Test Student",
        email="student@example.com",
        password="StrongPass123",
    )

    register_user(db, user_data)

    user = authenticate_user(
        db,
        "student@example.com",
        "WrongPassword123",
    )

    assert user is None


def test_inactive_user_cannot_login(db):
    user_data = UserRegister(
        full_name="Inactive Student",
        email="inactive@example.com",
        password="StrongPass123",
    )

    user = register_user(db, user_data)
    user.is_active = False
    db.commit()

    result = authenticate_user(
        db,
        "inactive@example.com",
        "StrongPass123",
    )

    assert result is None