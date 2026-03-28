"""
Scan model for security scan jobs
"""

from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum as SQLEnum
from datetime import datetime
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


class Scan(Base):
    """
    Scan model representing a security scan job
    """
    __tablename__ = "scans"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Scan details
    name = Column(String(255), nullable=False)
    description = Column(Text)
    scan_type = Column(SQLEnum(ScanType), nullable=False)
    target = Column(String(255), nullable=False, index=True)
    
    # Status
    status = Column(SQLEnum(ScanStatus), default=ScanStatus.PENDING, nullable=False, index=True)
    progress = Column(String(5), default="0")  # Percentage as string
    
    # Configuration (stored as JSON string)
    scan_config = Column(Text)  # JSON configuration for scan
    
    # Results
    result_summary = Column(Text)  # JSON summary of findings
    full_results_path = Column(String(500))  # Path to full results in MinIO
    
    # Error tracking
    error_message = Column(Text)
    
    # Task tracking
    celery_task_id = Column(String(100), index=True)
    worker_name = Column(String(100))
    
    # Multi-tenancy
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Scan(id={self.id}, name={self.name}, status={self.status})>"
