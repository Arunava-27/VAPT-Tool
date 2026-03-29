"""
User management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ....db.session import get_db
from ....models.user import User
from ....schemas.user import UserResponse, UserCreate, UserUpdate, ProfileUpdate, ChangePasswordRequest
from ....core.security import hash_password, verify_password
from .auth import get_current_active_user

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user profile"""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_own_profile(
    profile_data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update own profile (full_name and/or email)"""
    update = profile_data.dict(exclude_unset=True)

    if "email" in update and update["email"] != current_user.email:
        existing = db.query(User).filter(User.email == update["email"]).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")

    for field, value in update.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_own_password(
    password_data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Change own password — requires current password for verification"""
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = hash_password(password_data.new_password)
    db.commit()


@router.get("/", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    List users (filtered by tenant for non-superusers)
    
    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        db: Database session
        current_user: Current authenticated user
    
    Returns:
        List of users
    """
    query = db.query(User)
    
    # Non-superusers can only see users in their tenant
    if not current_user.is_superuser:
        query = query.filter(User.tenant_id == current_user.tenant_id)
    
    users = query.offset(skip).limit(limit).all()
    return users


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get user by ID
    
    Args:
        user_id: User ID
        db: Database session
        current_user: Current authenticated user
    
    Returns:
        User details
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Non-superusers can only view users in their tenant
    if not current_user.is_superuser and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return user


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new user
    
    Args:
        user_data: User creation data
        db: Database session
        current_user: Current authenticated user
    
    Returns:
        Created user
    """
    # Check if user has permission
    if not current_user.has_permission("manage_users"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Non-superusers can only create users in their own tenant
    if not current_user.is_superuser and user_data.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot create users in other tenants")
    
    # Create user
    new_user = User(
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        is_active=user_data.is_active,
        tenant_id=user_data.tenant_id
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update user
    
    Args:
        user_id: User ID
        user_data: User update data
        db: Database session
        current_user: Current authenticated user
    
    Returns:
        Updated user
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check permissions
    is_self = user.id == current_user.id
    if not is_self and not current_user.has_permission("manage_users"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Non-superusers can only update users in their tenant
    if not current_user.is_superuser and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update fields
    update_data = user_data.dict(exclude_unset=True)

    # Only superusers may toggle is_active or is_superuser
    if not current_user.is_superuser:
        update_data.pop("is_active", None)
        update_data.pop("is_superuser", None)
    
    if "password" in update_data:
        update_data["hashed_password"] = hash_password(update_data.pop("password"))
    
    for field, value in update_data.items():
        setattr(user, field, value)
    
    db.commit()
    db.refresh(user)
    
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Delete user
    
    Args:
        user_id: User ID
        db: Database session
        current_user: Current authenticated user
    """
    if not current_user.has_permission("manage_users"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Cannot delete self
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    # Non-superusers can only delete users in their tenant
    if not current_user.is_superuser and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    db.delete(user)
    db.commit()
