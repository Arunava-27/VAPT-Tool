"""
Pydantic v2 schemas for AuditLog operations.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel


class AuditLogCreate(BaseModel):
    """Schema for creating an audit log entry."""

    model_config = {"from_attributes": True}

    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Dict[str, Any] = {}
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuditLogResponse(BaseModel):
    """Schema for audit log API responses."""

    model_config = {"from_attributes": True}

    id: int
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime
