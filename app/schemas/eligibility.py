from pydantic import BaseModel, ConfigDict, Field


class EligibilityRequirementCreate(BaseModel):
    requirement_type: str = Field(min_length=2, max_length=100)
    requirement_value: str = Field(min_length=2, max_length=255)
    is_mandatory: bool = True


class EligibilityRequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_id: int
    requirement_type: str
    requirement_value: str
    is_mandatory: bool


class EligibilityCheckItem(BaseModel):
    requirement_type: str
    requirement_value: str
    is_mandatory: bool
    satisfied: bool


class EligibilityCheckResponse(BaseModel):
    resource_id: int
    eligible: bool
    requirements: list[EligibilityCheckItem]