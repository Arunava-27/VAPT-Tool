"""
API v1 router - aggregates all endpoint routers
"""

from fastapi import APIRouter

from .endpoints import auth, scans, health, users

api_router = APIRouter()

# Health check
api_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"]
)

# Authentication
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["authentication"]
)

# Users
api_router.include_router(
    users.router,
    prefix="/users",
    tags=["users"]
)

# Scans
api_router.include_router(
    scans.router,
    prefix="/scans",
    tags=["scans"]
)
