"""
Authentication endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Dict

from ....db.session import get_db
from ....core.security import verify_password, create_access_token, create_refresh_token, decode_token, SecurityUtils
from ....models.user import User
from ....schemas.auth import Token, LoginRequest, RefreshTokenRequest

router = APIRouter()

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get current authenticated user from JWT token
    
    Args:
        token: JWT access token
        db: Database session
    
    Returns:
        Current user
    
    Raises:
        HTTPException: If token is invalid or user not found
    """
    # Decode token
    payload = decode_token(token)
    
    # Validate token type
    SecurityUtils.validate_token_type(payload, "access")
    
    # Get user ID from payload
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user (is_active already enforced by get_current_user)"""
    return current_user


@router.post("/login", response_model=Token)
async def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
) -> Dict:
    """
    Login endpoint - authenticate user and return JWT tokens
    
    Args:
        login_data: Login credentials
        db: Database session
    
    Returns:
        Access and refresh tokens
    """
    # Find user by email
    user = db.query(User).filter(User.email == login_data.email).first()
    
    # Verify user exists and password is correct
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Update last login
    user.last_login = datetime.now(timezone.utc)
    user.login_count = (user.login_count or 0) + 1
    db.commit()
    
    # Create tokens
    token_data = {
        "sub": str(user.id),
        "email": str(user.email),
        "tenant_id": str(user.tenant_id)
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
) -> Dict:
    """
    Refresh access token using refresh token
    
    Args:
        refresh_data: Refresh token
        db: Database session
    
    Returns:
        New access and refresh tokens
    """
    # Decode refresh token
    payload = decode_token(refresh_data.refresh_token)
    
    # Validate token type
    SecurityUtils.validate_token_type(payload, "refresh")
    
    # Get user
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Create new tokens
    token_data = {
        "sub": str(user.id),
        "email": str(user.email),
        "tenant_id": str(user.tenant_id)
    }
    
    access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer"
    }


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
) -> Dict:
    """
    Get current user information
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        User information
    """
    return {
        "id": str(current_user.id),
        "email": str(current_user.email),
        "full_name": current_user.full_name,
        "is_active": current_user.is_active,
        "is_superuser": current_user.is_superuser,
        "tenant_id": str(current_user.tenant_id),
        "roles": current_user.role_names,
        "permissions": list(current_user.permissions)
    }


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_active_user)
) -> Dict:
    """
    Logout endpoint (client should delete tokens)
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        Success message
    """
    return {"message": "Successfully logged out"}
