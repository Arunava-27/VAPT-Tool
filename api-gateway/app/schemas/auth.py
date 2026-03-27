"""
Pydantic schemas for authentication
"""

from pydantic import BaseModel, EmailStr
from typing import Optional


class Token(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Data extracted from JWT token"""
    email: Optional[str] = None
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None


class LoginRequest(BaseModel):
    """Login request"""
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str


class PasswordChangeRequest(BaseModel):
    """Password change request"""
    old_password: str
    new_password: str


class PasswordResetRequest(BaseModel):
    """Password reset request"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation"""
    token: str
    new_password: str
