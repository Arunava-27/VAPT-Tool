"""
Scan management endpoints (stub for now)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ....db.session import get_db
from .auth import get_current_active_user
from ....models.user import User

router = APIRouter()


@router.get("/")
async def list_scans(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    List scans (stub - will be fully implemented in Phase 3)
    
    Returns:
        List of scans
    """
    return {
        "message": "Scan listing endpoint - to be implemented in Phase 3",
        "user": current_user.email
    }


@router.post("/")
async def create_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create scan (stub - will be fully implemented in Phase 3)
    
    Returns:
        Created scan
    """
    return {
        "message": "Scan creation endpoint - to be implemented in Phase 3",
        "user": current_user.email
    }
