"""
Pydantic schemas for User model
"""

from pydantic import BaseModel, EmailStr, Field, field_validator, validator
from typing import Optional, List, Any
from datetime import datetime


class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool = True


class UserCreate(UserBase):
    """Schema for creating a user"""
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    tenant_id: str
    role_ids: Optional[List[str]] = []

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class UserUpdate(BaseModel):
    """Schema for updating a user"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8)


class ProfileUpdate(BaseModel):
    """Schema for a user updating their own profile"""
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None


class ChangePasswordRequest(BaseModel):
    """Schema for changing own password (requires current password)"""
    current_password: str
    new_password: str = Field(..., min_length=8, description="Must be at least 8 characters")
    confirm_password: str

    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v


class UserInDB(UserBase):
    """User schema as stored in database"""
    id: str
    tenant_id: str
    is_superuser: bool
    is_verified: bool
    last_login: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    """
    User schema for API responses.

    Uses plain str for email so that internal addresses (e.g. *.local,
    *.internal) are never rejected by email-validator at serialisation time.
    UUID primary keys are coerced to str automatically.
    """
    id: str
    email: str          # str, not EmailStr — avoids rejecting .local/.internal domains in responses
    full_name: Optional[str] = None
    is_active: bool = True
    tenant_id: str
    is_superuser: bool
    is_verified: bool
    role_names: List[str] = []
    created_at: datetime

    @field_validator('id', 'tenant_id', mode='before')
    @classmethod
    def coerce_uuid(cls, v: Any) -> str:
        return str(v) if v is not None else v

    @field_validator('email', mode='before')
    @classmethod
    def coerce_email(cls, v: Any) -> str:
        return str(v) if v is not None else v

    class Config:
        from_attributes = True

