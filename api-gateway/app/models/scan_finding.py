"""
ScanFinding model — denormalised findings table for fast querying and AI analysis.
"""

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
import uuid

from ..db.session import Base


class ScanFinding(Base):
    """
    ScanFinding model providing a denormalised view of scan findings.

    Optimised for fast querying across severity, tool, and tenant dimensions.
    """

    __tablename__ = "scan_findings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String(36), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True)
    vulnerability_id = Column(
        String(36), ForeignKey("vulnerabilities.id", ondelete="CASCADE"), nullable=True
    )
    tool = Column(String(50), nullable=False, index=True)
    finding_type = Column(String(100), nullable=True)
    severity = Column(String(20), nullable=True, index=True)
    target = Column(String(500), nullable=True)
    port = Column(Integer, nullable=True)
    service = Column(String(100), nullable=True)
    raw_data = Column(JSONB, nullable=True)
    ai_analysis = Column(JSONB, nullable=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<ScanFinding(id={self.id}, tool={self.tool!r}, severity={self.severity})>"
