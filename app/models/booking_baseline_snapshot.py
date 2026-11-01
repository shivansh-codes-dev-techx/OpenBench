from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    LargeBinary,
    String,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BookingBaselineSnapshot(Base):
    """An immutable baseline-image set captured for one approved booking."""

    __tablename__ = "booking_baseline_snapshots"
    __table_args__ = (
        UniqueConstraint("booking_id", "resource_id", name="uq_booking_baseline_snapshot_booking_resource"),
        UniqueConstraint("id", "booking_id", name="uq_booking_baseline_snapshot_id_booking"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id"), nullable=False, index=True
    )
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    booking: Mapped["Booking"] = relationship(back_populates="baseline_snapshot")
    resource: Mapped["Resource"] = relationship()
    created_by: Mapped["User"] = relationship()
    images: Mapped[list["BookingBaselineSnapshotImage"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="BookingBaselineSnapshotImage.angle",
    )


class BookingBaselineSnapshotImage(Base):
    """A copied baseline image. Its bytes are independent of the live resource baseline."""

    __tablename__ = "booking_baseline_snapshot_images"
    __table_args__ = (
        CheckConstraint(
            "angle IN ('FRONT', 'BACK', 'LEFT', 'RIGHT', 'TOP', 'BOTTOM')",
            name="ck_booking_baseline_snapshot_images_angle",
        ),
        UniqueConstraint(
            "snapshot_id",
            "angle",
            name="uq_booking_baseline_snapshot_images_snapshot_angle",
        ),
        UniqueConstraint(
            "booking_id",
            "angle",
            name="uq_booking_baseline_snapshot_images_booking_angle",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "booking_id"],
            ["booking_baseline_snapshots.id", "booking_baseline_snapshots.booking_id"],
            name="fk_booking_baseline_snapshot_image_snapshot_booking",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    snapshot_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    angle: Mapped[str] = mapped_column(String(10), nullable=False)
    source_baseline_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("resource_baseline_images.id", ondelete="SET NULL"), nullable=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    snapshot: Mapped["BookingBaselineSnapshot"] = relationship(back_populates="images")
    source_baseline_image: Mapped["ResourceBaselineImage | None"] = relationship()


def _reject_snapshot_mutation(mapper, connection, target) -> None:
    raise ValueError("Booking baseline snapshots are immutable")


# Protect normal ORM writes as well as the absence of update/delete API routes.
# The explicit SQLite rollback remains able to drop these tables as designed.
event.listen(BookingBaselineSnapshot, "before_update", _reject_snapshot_mutation)
event.listen(BookingBaselineSnapshot, "before_delete", _reject_snapshot_mutation)
event.listen(BookingBaselineSnapshotImage, "before_update", _reject_snapshot_mutation)
event.listen(BookingBaselineSnapshotImage, "before_delete", _reject_snapshot_mutation)
