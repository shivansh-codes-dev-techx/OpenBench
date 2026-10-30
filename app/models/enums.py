from enum import Enum


class UserRole(str, Enum):
    STUDENT = "STUDENT"
    OWNER = "OWNER"
    ADMIN = "ADMIN"


class ResourceType(str, Enum):
    EQUIPMENT = "EQUIPMENT"
    SPACE = "SPACE"


class BookingStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    IN_USE = "IN_USE"
    RETURNED = "RETURNED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class QualificationStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"