from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import QualificationStatus


class UserQualification(Base):
    __tablename__ = "user_qualifications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    qualification_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    qualification_title: Mapped[str] = mapped_column(
        String(150), nullable=False
    )

    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    evidence_reference: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    status: Mapped[QualificationStatus] = mapped_column(
        Enum(
            QualificationStatus,
            name="qualification_status",
            native_enum=False,
            values_callable=lambda enum_cls: [
                item.value for item in enum_cls
            ],
        ),
        default=QualificationStatus.PENDING,
        nullable=False,
    )

    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    review_note: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )