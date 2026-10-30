from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator

from app.models.enums import UserRole


class UserRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.STUDENT
    institution: str | None = Field(default=None, max_length=150)

    @field_validator("role")
    @classmethod
    def prevent_admin_registration(cls, value):
        if value == UserRole.ADMIN:
            raise ValueError("Admin registration is not allowed")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    role: UserRole
    institution: str | None
    is_active: bool