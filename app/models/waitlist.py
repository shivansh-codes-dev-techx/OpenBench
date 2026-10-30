from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Waitlist(Base):
    __tablename__ = "waitlist"

    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "user_id",
            name="uq_waitlist_resource_user",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id"), nullable=False, index=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )