from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConditionReportImageMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    image_id: int
    booking_id: int
    report_id: int
    angle: str
    stage: str
    mime_type: str
    byte_size: int
    sha256: str
    uploaded_at: datetime


class ConditionReportImageList(BaseModel):
    images: list[ConditionReportImageMetadata]
