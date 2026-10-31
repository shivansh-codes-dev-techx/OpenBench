from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EligibilityRequirement(Base):
    __tablename__ = "eligibility_requirements"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id"), nullable=False, index=True
    )

    requirement_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    requirement_value: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    is_mandatory: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )