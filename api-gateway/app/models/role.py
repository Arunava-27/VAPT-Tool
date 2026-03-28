"""
Role model for RBAC (Role-Based Access Control)
"""

from sqlalchemy import Column, String, Boolean, DateTime, Text, Table, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from ..db.session import Base


# Association table for many-to-many relationship between users and roles
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', String(36), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', String(36), ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)
)


class Role(Base):
    """
    Role model for access control
    
    Defines roles with specific permissions
    """
    __tablename__ = "roles"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True, index=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text)
    
    # Permissions (stored as JSON string)
    permissions = Column(Text, nullable=False, default='[]')
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_system_role = Column(Boolean, default=False, nullable=False)  # System roles can't be deleted
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    users = relationship("User", secondary=user_roles, back_populates="roles")
    
    def __repr__(self):
        return f"<Role(id={self.id}, name={self.name}, slug={self.slug})>"


# Default system roles and their permissions
SYSTEM_ROLES = {
    "super_admin": {
        "name": "Super Admin",
        "slug": "super_admin",
        "description": "Full system access across all tenants",
        "permissions": [
            "manage_tenants",
            "manage_users",
            "manage_roles",
            "manage_scans",
            "view_all_data",
            "manage_system_settings",
            "manage_api_keys",
            "view_audit_logs"
        ]
    },
    "tenant_admin": {
        "name": "Tenant Admin",
        "slug": "tenant_admin",
        "description": "Full access within their tenant",
        "permissions": [
            "manage_users",
            "manage_scans",
            "view_reports",
            "manage_settings",
            "view_audit_logs"
        ]
    },
    "analyst": {
        "name": "Security Analyst",
        "slug": "analyst",
        "description": "Can create and run scans, view results",
        "permissions": [
            "create_scans",
            "view_scans",
            "manage_own_scans",
            "view_reports",
            "export_results"
        ]
    },
    "viewer": {
        "name": "Viewer",
        "slug": "viewer",
        "description": "Read-only access to scans and reports",
        "permissions": [
            "view_scans",
            "view_reports"
        ]
    }
}
