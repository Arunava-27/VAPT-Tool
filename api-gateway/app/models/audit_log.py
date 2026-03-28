"""
AuditLog model for compliance and security event tracking.
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

from ..db.session import Base


class AuditLog(Base):
    """
    AuditLog model for tracking all user actions and system events.

    Used for compliance, forensics, and security monitoring.
    """

    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(255), nullable=True)
    details = Column(JSONB, default=dict, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action!r}, user_id={self.user_id})>"
