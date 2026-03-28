"""
Tenant model for multi-tenancy support
"""

from sqlalchemy import Column, String, Boolean, DateTime, Text
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
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True, index=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    
    # Contact information
    contact_email = Column(String(255))
    contact_name = Column(String(255))
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Schema/namespace for database isolation
    schema_name = Column(String(100), unique=True)
    
    # Settings (JSON field)
    settings = Column(Text)  # Store as JSON string
    
    # Limits and quotas
    max_users = Column(String(10), default="unlimited")
    max_scans_per_month = Column(String(10), default="unlimited")
    max_concurrent_scans = Column(String(5), default="5")
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Tenant(id={self.id}, name={self.name}, slug={self.slug})>"
