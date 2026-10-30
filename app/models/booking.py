from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import BookingStatus


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id"), nullable=False, index=True
    )

    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    purpose: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            name="booking_status",
            native_enum=False,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=BookingStatus.PENDING,
        nullable=False,
        index=True,
    )

    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    checkin_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    checkout_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    student: Mapped["User"] = relationship(
        back_populates="bookings",
        foreign_keys=[student_id],
    )
    resource: Mapped["Resource"] = relationship(back_populates="bookings")
    approver: Mapped["User | None"] = relationship(
        foreign_keys=[approved_by_id]
    )