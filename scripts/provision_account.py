"""Provision a trusted OWNER or ADMIN account using the configured database."""

import argparse
from getpass import getpass

from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.database import SessionLocal
from app.models.enums import UserRole
from app.models.user import User


class OwnerDetails(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    institution: str | None = Field(default=None, max_length=150)


def provision_account(
    db: Session,
    *,
    full_name: str,
    email: str,
    password: str,
    role: UserRole,
    institution: str | None = None,
) -> User:
    try:
        details = OwnerDetails(
            full_name=full_name.strip(),
            email=email.strip(),
            institution=institution.strip() if institution else None,
        )
    except ValidationError:
        raise ValueError("Invalid account details") from None

    if role not in (UserRole.OWNER, UserRole.ADMIN):
        raise ValueError("Only OWNER or ADMIN accounts can be provisioned")
    if not 8 <= len(password) <= 128:
        raise ValueError("Password must be between 8 and 128 characters")

    normalized_email = str(details.email).lower()
    user = User(
        full_name=details.full_name,
        email=normalized_email,
        hashed_password=hash_password(password),
        role=role,
        institution=details.institution,
        is_active=True,
    )

    try:
        with db.begin():
            existing = db.scalar(
                select(User.id).where(User.email == normalized_email)
            )
            if existing is not None:
                raise ValueError("An account with that email already exists")

            db.add(user)
            db.flush()
    except IntegrityError:
        raise ValueError(
            "An account with that email already exists"
        ) from None

    return user


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("OWNER", "ADMIN"))
    args = parser.parse_args()
    role = UserRole(args.role)

    try:
        full_name = input("Account holder full name: ").strip()
        email = input("Account email: ").strip()
        institution = input("Institution (optional): ").strip() or None
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nAccount provisioning cancelled") from None

    password = getpass("Password (8-128 characters): ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")

    try:
        with SessionLocal() as db:
            user = provision_account(
                db,
                full_name=full_name,
                email=email,
                password=password,
                role=role,
                institution=institution,
            )
            user_id = user.id
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    except SQLAlchemyError:
        raise SystemExit(
            "Account provisioning failed because the database operation failed"
        ) from None

    print(f"Provisioned {role.value} account (user id {user_id}).")


if __name__ == "__main__":
    main()
