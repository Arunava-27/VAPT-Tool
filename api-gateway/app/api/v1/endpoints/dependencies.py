"""
Role-Based Access Control dependencies and utilities
"""

from fastapi import Depends, HTTPException, status
from typing import List

from ..models.user import User
from .auth import get_current_active_user


class PermissionChecker:
    """
    Dependency class to check user permissions
    
    Usage:
        @router.get("/endpoint", dependencies=[Depends(PermissionChecker(["manage_scans"]))])
    """
    
    def __init__(self, required_permissions: List[str]):
        self.required_permissions = required_permissions
    
    def __call__(self, current_user: User = Depends(get_current_active_user)):
        """
        Check if user has required permissions
        
        Args:
            current_user: Current authenticated user
        
        Raises:
            HTTPException: If user doesn't have required permissions
        """
        if current_user.is_superuser:
            # Superusers bypass all permission checks
            return
        
        user_permissions = current_user.permissions
        
        for permission in self.required_permissions:
            if permission not in user_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission} required"
                )


class RoleChecker:
    """
    Dependency class to check user roles
    
    Usage:
        @router.get("/endpoint", dependencies=[Depends(RoleChecker(["admin", "analyst"]))])
    """
    
    def __init__(self, required_roles: List[str]):
        self.required_roles = required_roles
    
    def __call__(self, current_user: User = Depends(get_current_active_user)):
        """
        Check if user has any of the required roles
        
        Args:
            current_user: Current authenticated user
        
        Raises:
            HTTPException: If user doesn't have any of the required roles
        """
        if current_user.is_superuser:
            return
        
        user_roles = current_user.role_names
        
        if not any(role in user_roles for role in self.required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: one of {self.required_roles} roles required"
            )


def require_superuser(current_user: User = Depends(get_current_active_user)):
    """
    Dependency to require superuser access
    
    Usage:
        @router.get("/endpoint", dependencies=[Depends(require_superuser)])
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required"
        )
