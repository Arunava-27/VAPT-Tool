from fastapi import APIRouter

from .endpoints import auth, scans, health, users, ai, infra, ws, setup, roles, network, logs

api_router = APIRouter()

# Health check
api_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"]
)

# Infrastructure / services monitor
api_router.include_router(
    infra.router,
    prefix="/health",
    tags=["infrastructure"]
)

# First-run setup (public — no auth required)
api_router.include_router(
    setup.router,
    prefix="/setup",
    tags=["setup"]
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

# Roles
api_router.include_router(
    roles.router,
    prefix="/roles",
    tags=["roles"]
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

# WebSocket — real-time scan status
api_router.include_router(
    ws.router,
    prefix="/ws",
    tags=["websocket"]
)

# Network discovery and node VAPT
api_router.include_router(
    network.router,
    prefix="/network",
    tags=["network"]
)

# Docker container logs
api_router.include_router(
    logs.router,
    prefix="/logs",
    tags=["logs"]
)
