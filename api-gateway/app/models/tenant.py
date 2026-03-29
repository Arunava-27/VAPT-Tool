"""
Tenant model for multi-tenancy support
"""

from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from ..db.session import Base


class Tenant(Base):
    """
    Tenant model for multi-tenant isolation
    
    Each tenant represents an organization or customer using the platform
    """
    __tablename__ = "tenants"
    
    id = Column(PGUUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True, index=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    
    # Contact information
    contact_email = Column(String(255))
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Schema/namespace for database isolation
    schema_name = Column(String(100), unique=True)
    
    # Settings (JSONB)
    settings = Column(JSONB, default=dict, nullable=True)
    
    # Limits and quotas (match DB column names)
    max_users = Column(Integer, default=10)
    max_scans = Column(Integer, default=100)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Tenant(id={self.id}, name={self.name}, slug={self.slug})>"
