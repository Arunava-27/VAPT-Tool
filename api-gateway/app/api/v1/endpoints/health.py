"""
Health check endpoints
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any

from ....db.session import get_db
from ....core.config import settings

router = APIRouter()


@router.get("/")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check
    
    Returns service status and version
    """
    return {
        "status": "healthy",
        "service": "api-gateway",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT
    }


@router.get("/db")
async def database_health(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Database health check
    
    Verifies database connectivity
    """
    try:
        # Execute a simple query
        db.execute("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }


@router.get("/ready")
async def readiness_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Readiness check for Kubernetes/orchestration
    
    Checks if service is ready to accept traffic
    """
    checks = {
        "api": "ready",
        "database": "checking"
    }
    
    try:
        db.execute("SELECT 1")
        checks["database"] = "ready"
        overall_status = "ready"
    except Exception as e:
        checks["database"] = "not_ready"
        overall_status = "not_ready"
    
    return {
        "status": overall_status,
        "checks": checks
    }


@router.get("/live")
async def liveness_check() -> Dict[str, Any]:
    """
    Liveness check for Kubernetes/orchestration
    
    Indicates if service is alive (even if not ready)
    """
    return {
        "status": "alive"
    }
