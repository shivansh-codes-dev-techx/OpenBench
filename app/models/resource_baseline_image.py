from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ResourceBaselineImage(Base):
    """The owner-managed, canonical image for one resource inspection angle."""

    __tablename__ = "resource_baseline_images"
    __table_args__ = (
        CheckConstraint(
            "angle IN ('FRONT', 'BACK', 'LEFT', 'RIGHT', 'TOP', 'BOTTOM')",
            name="ck_resource_baseline_images_angle",
        ),
        UniqueConstraint(
            "resource_id",
            "angle",
            name="uq_resource_baseline_images_resource_angle",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    angle: Mapped[str] = mapped_column(String(10), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    quality_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    resource: Mapped["Resource"] = relationship(back_populates="baseline_images")
    uploader: Mapped["User"] = relationship()
