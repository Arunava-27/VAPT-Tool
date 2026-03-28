"""
User model for authentication and authorization
"""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from ..db.session import Base
from .role import user_roles


class User(Base):
    """
    User model for authentication
    
    Represents a user account with authentication and tenant association
    """
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    
    # Status flags
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    # Multi-tenancy
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Password reset
    reset_token = Column(String(255), nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    
    # Last login tracking
    last_login = Column(DateTime, nullable=True)
    login_count = Column(String(10), default="0")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, tenant_id={self.tenant_id})>"
    
    @property
    def role_names(self) -> list:
        """Get list of role names"""
        return [role.slug for role in self.roles]
    
    @property
    def permissions(self) -> set:
        """Get combined permissions from all roles"""
        import json
        perms = set()
        for role in self.roles:
            role_perms = json.loads(role.permissions) if role.permissions else []
            perms.update(role_perms)
        return perms
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission"""
        return self.is_superuser or permission in self.permissions
    
    def has_role(self, role_slug: str) -> bool:
        """Check if user has a specific role"""
        return role_slug in self.role_names
