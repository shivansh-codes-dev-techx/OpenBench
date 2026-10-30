from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=UserRole.STUDENT,
        nullable=False,
    )

    institution: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    resources: Mapped[list["Resource"]] = relationship(
    back_populates="owner"
    )

    bookings: Mapped[list["Booking"]] = relationship(
    back_populates="student",
    foreign_keys="Booking.student_id",
    )