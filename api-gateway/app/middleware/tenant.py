"""
Multi-tenant context middleware
"""

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session

from ..db.session import SessionLocal
from ..models.user import User
from ..core.security import decode_token


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract and validate tenant context from JWT token
    
    Adds tenant_id to request.state for use in downstream handlers
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and add tenant context
        
        Args:
            request: FastAPI request
            call_next: Next middleware/handler
        
        Returns:
            Response
        """
        # Skip tenant validation for public endpoints
        public_paths = ["/", "/health", "/api/v1/health", "/api/v1/auth/login", "/docs", "/openapi.json"]
        
        if request.url.path in public_paths or request.url.path.startswith("/docs"):
            response = await call_next(request)
            return response
        
        # Try to extract tenant from authorization header
        auth_header = request.headers.get("Authorization")
        
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
            try:
                payload = decode_token(token)
                tenant_id = payload.get("tenant_id")
                
                if tenant_id:
                    # Add tenant_id to request state
                    request.state.tenant_id = tenant_id
                    request.state.user_id = payload.get("sub")
            
            except Exception:
                # Invalid token - let auth dependency handle it
                pass
        
        response = await call_next(request)
        return response


def get_current_tenant_id(request: Request) -> str:
    """
    Dependency to get current tenant ID from request state
    
    Args:
        request: FastAPI request
    
    Returns:
        Tenant ID
    
    Raises:
        HTTPException: If tenant context not found
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context not found"
        )
    
    return tenant_id
