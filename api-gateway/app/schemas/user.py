"""
Pydantic schemas for User model
"""

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
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
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class UserUpdate(BaseModel):
    """Schema for updating a user"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8)


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


class UserResponse(UserBase):
    """User schema for API responses"""
    id: str
    tenant_id: str
    is_superuser: bool
    is_verified: bool
    role_names: List[str] = []
    created_at: datetime
    
    class Config:
        from_attributes = True
