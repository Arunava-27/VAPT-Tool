"""
Scan model for security scan jobs
"""

from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from datetime import datetime, timezone
import uuid
import enum

from ..db.session import Base


class ScanStatus(str, enum.Enum):
    """Scan status enumeration"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScanType(str, enum.Enum):
    """Scan type enumeration"""
    NETWORK = "network"
    WEB = "web"
    CONTAINER = "container"
    CLOUD = "cloud"
    CUSTOM = "custom"
    FULL = "full"
    COMPREHENSIVE = "comprehensive"


class Scan(Base):
    """
    Scan model representing a security scan job
    """
    __tablename__ = "scans"
    
    id = Column(PGUUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Scan details
    name = Column(String(255), nullable=False)
    description = Column(Text)
    scan_type = Column(String(50), nullable=False)
    target = Column(String(500), nullable=False, index=True)
    
    # Status
    status = Column(String(50), default="pending", nullable=False, index=True)
    
    # Configuration (stored as JSONB in postgres)
    scan_config = Column(JSONB, default=dict)
    
    # Results
    result_summary = Column(JSONB)
    
    # Error tracking
    error = Column(Text)
    
    # Multi-tenancy
    tenant_id = Column(PGUUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = Column(PGUUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Scan(id={self.id}, name={self.name}, status={self.status}))>"
