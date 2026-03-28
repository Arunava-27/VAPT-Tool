"""
Rate limiting middleware
"""

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
import time
from collections import defaultdict
from typing import Dict, Tuple
import asyncio

from ..core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiting middleware
    
    Limits requests per minute based on IP address
    For production, consider using Redis for distributed rate limiting
    """
    
    def __init__(self, app):
        super().__init__(app)
        # Store: {ip: [(timestamp, count)]}
        self.requests: Dict[str, list] = defaultdict(list)
        self.cleanup_task = None
    
    async def dispatch(self, request: Request, call_next):
        """
        Check rate limit before processing request
        
        Args:
            request: FastAPI request
            call_next: Next middleware/handler
        
        Returns:
            Response or rate limit error
        """
        if not settings.RATE_LIMIT_ENABLED:
            response = await call_next(request)
            return response
        
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/api/v1/health/live", "/api/v1/health/ready"]:
            response = await call_next(request)
            return response
        
        # Get client IP
        client_ip = request.client.host
        
        # Check if user is authenticated (from auth header)
        is_authenticated = bool(request.headers.get("Authorization"))
        
        # Set rate limit based on authentication
        if is_authenticated:
            rate_limit = settings.RATE_LIMIT_PER_MINUTE
        else:
            rate_limit = settings.RATE_LIMIT_PER_MINUTE_UNAUTH
        
        # Check rate limit
        current_time = time.time()
        minute_ago = current_time - 60
        
        # Clean old requests
        self.requests[client_ip] = [
            (ts, count) for ts, count in self.requests[client_ip]
            if ts > minute_ago
        ]
        
        # Count requests in last minute
        total_requests = sum(count for _, count in self.requests[client_ip])
        
        if total_requests >= rate_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {rate_limit} requests per minute allowed."
            )
        
        # Add current request
        self.requests[client_ip].append((current_time, 1))
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(rate_limit - total_requests - 1)
        response.headers["X-RateLimit-Reset"] = str(int(current_time + 60))
        
        return response
    
    async def cleanup_old_entries(self):
        """Periodically cleanup old entries to prevent memory leak"""
        while True:
            await asyncio.sleep(300)  # Run every 5 minutes
            
            current_time = time.time()
            minute_ago = current_time - 60
            
            # Remove old entries
            for ip in list(self.requests.keys()):
                self.requests[ip] = [
                    (ts, count) for ts, count in self.requests[ip]
                    if ts > minute_ago
                ]
                
                # Remove IP if no recent requests
                if not self.requests[ip]:
                    del self.requests[ip]
