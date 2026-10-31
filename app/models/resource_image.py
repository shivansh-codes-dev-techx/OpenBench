
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ResourceImage(Base):
    __tablename__ = "resource_images"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    mime_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    byte_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    image_data: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    resource: Mapped["Resource"] = relationship(
        back_populates="images",
    )

    uploader: Mapped["User"] = relationship()

    @property
    def url(self) -> str:
        return f"/resources/{self.resource_id}/images/{self.id}"


Index(
    "uq_resource_images_one_primary",
    ResourceImage.resource_id,
    unique=True,
    sqlite_where=ResourceImage.is_primary.is_(True),
    postgresql_where=ResourceImage.is_primary.is_(True),
)
