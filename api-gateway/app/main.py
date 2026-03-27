"""
Main FastAPI application
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from .core.config import settings
from .api.v1.api import api_router
from .db.session import init_db
from .middleware.tenant import TenantContextMiddleware
from .middleware.rate_limit import RateLimitMiddleware

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="VAPT Platform - AI-Driven Security Testing Platform",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json"
)


# Add middlewares (order matters - last added is executed first)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting (before tenant context)
if settings.RATE_LIMIT_ENABLED:
    app.add_middleware(RateLimitMiddleware)
    logger.info("Rate limiting enabled")

# Tenant Context
if settings.MULTI_TENANT_ENABLED:
    app.add_middleware(TenantContextMiddleware)
    logger.info("Multi-tenant mode enabled")


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "VAPT Platform API",
        "version": settings.APP_VERSION,
        "status": "operational",
        "docs": f"{settings.API_V1_PREFIX}/docs" if settings.DEBUG else "disabled"
    }


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT
    }


# Include API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting VAPT Platform API Gateway...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(f"Multi-tenant: {settings.MULTI_TENANT_ENABLED}")
    logger.info(f"Rate limiting: {settings.RATE_LIMIT_ENABLED}")
    
    # Initialize database
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
    
    logger.info("API Gateway ready!")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down API Gateway...")


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle uncaught exceptions"""
    logger.error(f"Uncaught exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc) if settings.DEBUG else "An error occurred"
        }
    )
