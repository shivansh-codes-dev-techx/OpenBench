from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConditionReport(Base):
    __tablename__ = "condition_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id"), nullable=False, index=True
    )

    submitted_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    report_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )

    condition_description: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    evidence_reference: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )