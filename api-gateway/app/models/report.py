"""
Report model for storing generated security scan reports.
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
import uuid

from ..db.session import Base


class Report(Base):
    """
    Report model representing a generated security report for a scan.

    Supports multiple formats (JSON, HTML, PDF) and types (full, executive, technical).
    """

    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String(36), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    report_type = Column(String(50), default="full", nullable=True)     # full/executive/technical
    status = Column(String(50), default="generating", nullable=True, index=True)  # generating/ready/failed
    format = Column(String(20), default="json", nullable=True)           # json/html/pdf
    content = Column(JSONB, nullable=True)                                # structured report data
    file_path = Column(String(500), nullable=True)                        # MinIO path for HTML/PDF
    generated_by = Column(String(50), default="ai", nullable=True)       # ai/manual
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def __repr__(self) -> str:
        return f"<Report(id={self.id}, title={self.title!r}, status={self.status})>"
