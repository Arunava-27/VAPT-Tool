"""
Report model for storing generated security scan reports.
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from datetime import datetime, timezone
import uuid

from ..db.session import Base


class Report(Base):
    """
    Report model representing a generated security report for a scan.

    Supports multiple formats (JSON, HTML, PDF) and types (full, executive, technical).
    """

    __tablename__ = "reports"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(UUID(as_uuid=False), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    report_type = Column(String(50), default="full", nullable=True)
    status = Column(String(50), default="generating", nullable=True, index=True)
    format = Column(String(20), default="json", nullable=True)
    content = Column(JSONB, nullable=True)
    file_path = Column(String(500), nullable=True)
    generated_by = Column(String(50), default="ai", nullable=True)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<Report(id={self.id}, title={self.title!r}, status={self.status})>"
