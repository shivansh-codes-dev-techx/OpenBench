from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id"), nullable=False, index=True
    )

    reported_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    title: Mapped[str] = mapped_column(
        String(150), nullable=False
    )

    description: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    severity: Mapped[str] = mapped_column(
        String(30), default="MEDIUM", nullable=False
    )

    resolution_note: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )