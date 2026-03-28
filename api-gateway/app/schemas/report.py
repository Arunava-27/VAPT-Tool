"""
Pydantic v2 schemas for Report CRUD operations.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel


class ReportCreate(BaseModel):
    """Schema for creating a new report."""

    model_config = {"from_attributes": True}

    scan_id: str
    title: str
    report_type: str = "full"       # full/executive/technical
    format: str = "json"            # json/html/pdf
    content: Optional[Dict[str, Any]] = None
    file_path: Optional[str] = None
    generated_by: str = "ai"        # ai/manual
    tenant_id: Optional[str] = None


class ReportResponse(BaseModel):
    """Schema for report API responses."""

    model_config = {"from_attributes": True}

    id: str
    scan_id: str
    title: str
    report_type: Optional[str] = None
    status: Optional[str] = None
    format: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    file_path: Optional[str] = None
    generated_by: Optional[str] = None
    tenant_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
