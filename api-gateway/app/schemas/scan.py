"""
Scan schemas for API requests/responses
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


# Import enums from orchestrator
class ScanType(str, Enum):
    """Types of scans"""
    NETWORK = "network"
    WEB = "web"
    CONTAINER = "container"
    CLOUD = "cloud"
    CUSTOM = "custom"
    COMPREHENSIVE = "comprehensive"


class ScanProfile(str, Enum):
    """Scan profiles"""
    QUICK = "quick"
    COMPREHENSIVE = "comprehensive"
    TARGETED = "targeted"
    AI_DRIVEN = "ai_driven"
    STEALTH = "stealth"
    COMPLIANCE = "compliance"


class ScanPriority(str, Enum):
    """Scan priority"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# Request schemas
class ScanTarget(BaseModel):
    """Scan target"""
    type: str
    value: str
    ports: Optional[List[int]] = None
    excludes: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class ScanOptions(BaseModel):
    """Scan options"""
    profile: ScanProfile = ScanProfile.COMPREHENSIVE
    timeout: int = 3600
    max_parallel_workers: int = 5
    include_exploits: bool = False
    stealth_mode: bool = False
    custom_options: Optional[Dict[str, Any]] = None


class ScanCreate(BaseModel):
    """Create scan request"""
    name: str
    description: Optional[str] = None
    scan_type: ScanType
    targets: List[ScanTarget]
    options: ScanOptions = Field(default_factory=ScanOptions)
    priority: ScanPriority = ScanPriority.NORMAL
    tags: Optional[List[str]] = None


class ScanUpdate(BaseModel):
    """Update scan request"""
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None


# Response schemas
class ScanResponse(BaseModel):
    """Scan response"""
    id: UUID
    name: str
    description: Optional[str]
    scan_type: str
    target: str
    status: str
    scan_config: Optional[Dict[str, Any]]
    result_summary: Optional[Dict[str, Any]]
    error: Optional[str]
    tenant_id: UUID
    created_by_id: UUID
    created_at: datetime
    updated_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ScanListResponse(BaseModel):
    """List of scans"""
    total: int
    scans: List[ScanResponse]


class ScanStatusResponse(BaseModel):
    """Scan status"""
    id: UUID
    status: str
    progress_percentage: int
    current_phase: str
    vulnerabilities_found: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error: Optional[str]
