from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.enums import UserRole
from app.schemas.user import UserRegister
from app.core.security import hash_password, verify_password


def register_user(db: Session, user_data: UserRegister) -> User:
    # Defense-in-depth: public registration cannot create ADMIN.
    if user_data.role == UserRole.ADMIN:
        raise ValueError("Admin registration is not allowed")

    email = str(user_data.email).lower()

    existing_user = db.scalar(
        select(User).where(User.email == email)
    )

    if existing_user:
        raise ValueError("Email already registered")

    new_user = User(
        full_name=user_data.full_name,
        email=email,
        hashed_password=hash_password(user_data.password),
        role=user_data.role,
        institution=user_data.institution,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user

    except IntegrityError:
        db.rollback()
        raise ValueError("Email already registered")


def authenticate_user(
    db: Session,
    email: str,
    password: str,
) -> User | None:

    normalized_email = email.lower()

    user = db.scalar(
        select(User).where(User.email == normalized_email)
    )

    if not user:
        return None

    if not user.is_active:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user