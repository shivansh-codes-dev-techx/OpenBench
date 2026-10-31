import pytest

from fastapi import HTTPException

from app.core.dependencies import require_roles
from app.models.user import User
from app.models.enums import UserRole


def make_user(role):
    return User(
        id=1,
        full_name="Test User",
        email="test@example.com",
        hashed_password="not-used",
        role=role,
        is_active=True,
    )


def test_student_access_allowed():
    checker = require_roles(UserRole.STUDENT)
    user = make_user(UserRole.STUDENT)

    assert checker(user) == user


def test_owner_access_allowed():
    checker = require_roles(UserRole.OWNER)
    user = make_user(UserRole.OWNER)

    assert checker(user) == user


def test_admin_access_allowed():
    checker = require_roles(UserRole.ADMIN)
    user = make_user(UserRole.ADMIN)

    assert checker(user) == user


def test_student_cannot_access_admin_resource():
    checker = require_roles(UserRole.ADMIN)
    user = make_user(UserRole.STUDENT)

    with pytest.raises(HTTPException) as exc:
        checker(user)

    assert exc.value.status_code == 403


def test_owner_cannot_access_student_only_resource():
    checker = require_roles(UserRole.STUDENT)
    user = make_user(UserRole.OWNER)

    with pytest.raises(HTTPException) as exc:
        checker(user)

    assert exc.value.status_code == 403


def test_multiple_roles_allowed():
    checker = require_roles(UserRole.OWNER, UserRole.ADMIN)
    user = make_user(UserRole.ADMIN)

    assert checker(user) == user