from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    action: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    entity_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    entity_id: Mapped[int | None] = mapped_column(
        nullable=True
    )

    details: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )