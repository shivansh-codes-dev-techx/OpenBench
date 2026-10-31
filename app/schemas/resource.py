
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ResourceType


class ResourceCreate(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    description: str | None = None
    category: str = Field(min_length=2, max_length=100)
    resource_type: ResourceType
    location: str = Field(min_length=2, max_length=200)
    usage_rules: str | None = None
    available_from: datetime | None = None
    available_until: datetime | None = None

    @model_validator(mode="after")
    def validate_availability(self):
        if (
            self.available_from is not None
            and self.available_until is not None
            and self.available_until <= self.available_from
        ):
            raise ValueError("Availability end must be after start")
        return self


class ResourceUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=150)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    usage_rules: str | None = None
    available_from: datetime | None = None
    available_until: datetime | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_availability(self):
        if (
            self.available_from is not None
            and self.available_until is not None
            and self.available_until <= self.available_from
        ):
            raise ValueError("Availability end must be after start")
        return self


class ResourceImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str


class ResourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    title: str
    description: str | None
    category: str
    resource_type: ResourceType
    location: str
    usage_rules: str | None
    available_from: datetime | None
    available_until: datetime | None
    is_active: bool
    created_at: datetime

    primary_image_url: str | None = None
    images: list[ResourceImageResponse] = Field(default_factory=list)