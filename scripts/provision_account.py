"""Provision a trusted OWNER or ADMIN account using the configured database."""

import argparse
from getpass import getpass

from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.database import SessionLocal
from app.models.enums import UserRole
from app.models.user import User


class OwnerDetails(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("OWNER", "ADMIN"))
    args = parser.parse_args()
    role = UserRole(args.role)

    try:
        details = OwnerDetails(
            full_name=input("Owner full name: ").strip(),
            email=input("Owner email: ").strip(),
        )
    except ValidationError as exc:
        raise SystemExit(f"Invalid owner details: {exc}") from None

    password = getpass("Temporary password (8-128 characters): ")
    confirmation = getpass("Confirm temporary password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    if not 8 <= len(password) <= 128:
        raise SystemExit("Password must be between 8 and 128 characters")

    email = str(details.email).lower()
    with SessionLocal() as db:
        existing = db.scalar(select(User.id).where(User.email == email))
        if existing is not None:
            raise SystemExit("An account with that email already exists")

        user = User(
            full_name=details.full_name,
            email=email,
            hashed_password=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise SystemExit(
                "Owner provisioning failed because the account already exists"
            ) from None
        db.refresh(user)

    print(f"Provisioned {role.value} account {email} (id {user.id})")


if __name__ == "__main__":
    main()
