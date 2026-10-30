from typing import Any

from pydantic import BaseModel


class APIResponse(BaseModel):
    success: bool
    message: str
    data: Any = None


class APIError(BaseModel):
    success: bool = False
    message: str
    error_code: str
    details: Any = None