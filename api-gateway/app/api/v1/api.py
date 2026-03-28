from fastapi import APIRouter

from .endpoints import auth, scans, health, users, ai

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

# AI Engine (proxy)
api_router.include_router(
    ai.router,
    prefix="/ai",
    tags=["ai-engine"]
)
