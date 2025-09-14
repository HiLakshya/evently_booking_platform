"""
Rate limiting middleware with Redis backend.
"""

import logging
import time
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..utils.exceptions import RateLimitError
from ..cache import get_cache

logger = logging.getLogger(__name__)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using sliding window algorithm."""
    
    def __init__(
        self,
        app,
        default_limit: int = 100,
        default_window: int = 60,
        burst_limit: int = 20,
        burst_window: int = 1
    ):
        super().__init__(app)
        self.default_limit = default_limit
        self.default_window = default_window
        self.burst_limit = burst_limit
        self.burst_window = burst_window
        self.cache = get_cache()
        
        # Define rate limits for different endpoints
        self.endpoint_limits = {
            "/api/v1/bookings": {"limit": 10, "window": 60},  # Booking endpoints
            "/api/v1/auth/login": {"limit": 5, "window": 300},  # Login attempts
            "/api/v1/auth/register": {"limit": 3, "window": 300},  # Registration
            "/api/v1/events": {"limit": 50, "window": 60},  # Event browsing
        }
    
    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting based on client IP and endpoint."""
        
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/", "/docs", "/redoc"]:
            return await call_next(request)
        
        client_ip = self._get_client_ip(request)
        endpoint = self._get_endpoint_pattern(request.url.path)
        
        # Check burst rate limit
        burst_exceeded, burst_retry_after = await self._check_burst_limit(client_ip)
        if burst_exceeded:
            return self._create_rate_limit_response(
                self.burst_limit,
                self.burst_window,
                burst_retry_after
            )
        
        # Check endpoint-specific rate limit
        limit_exceeded, retry_after = await self._check_rate_limit(client_ip, endpoint, request)
        if limit_exceeded:
            limit_config = self.endpoint_limits.get(endpoint, {
                "limit": self.default_limit,
                "window": self.default_window
            })
            return self._create_rate_limit_response(
                limit_config["limit"],
                limit_config["window"],
                retry_after
            )
        
        # Record the request
        await self._record_request(client_ip, endpoint)
        
        response = await call_next(request)
        
        # Add rate limit headers to response
        await self._add_rate_limit_headers(response, client_ip, endpoint)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request."""
        # Check for forwarded headers (be careful with these in production)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"
    
    def _get_endpoint_pattern(self, path: str) -> str:
        """Map request path to endpoint pattern for rate limiting."""
        # Match specific patterns
        for pattern in self.endpoint_limits.keys():
            if path.startswith(pattern):
                return pattern
        
        # Default pattern
        return "default"
    
    async def _check_burst_limit(self, client_ip: str) -> Tuple[bool, int]:
        """Check if client has exceeded burst rate limit."""
        key = f"rate_limit:burst:{client_ip}"
        current_time = int(time.time())
        
        try:
            # Use Redis pipeline for atomic operations
            pipe = self.cache.pipeline()
            
            # Remove old entries (outside window)
            pipe.zremrangebyscore(key, 0, current_time - self.burst_window)
            
            # Count current requests in window
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(current_time): current_time})
            
            # Set expiration
            pipe.expire(key, self.burst_window * 2)
            
            results = await pipe.execute()
            current_count = results[1]
            
            if current_count >= self.burst_limit:
                # Calculate retry after
                oldest_request = await self.cache.zrange(key, 0, 0, withscores=True)
                if oldest_request:
                    oldest_time = int(oldest_request[0][1])
                    retry_after = max(1, oldest_time + self.burst_window - current_time)
                    return True, retry_after
            
            return False, 0
            
        except Exception as e:
            logger.error(f"Error checking burst rate limit: {e}")
            # Fail open - allow request if Redis is down
            return False, 0
    
    async def _check_rate_limit(self, client_ip: str, endpoint: str, request: Request) -> Tuple[bool, int]:
        """Check if client has exceeded rate limit for specific endpoint."""
        limit_config = self.endpoint_limits.get(endpoint, {
            "limit": self.default_limit,
            "window": self.default_window
        })
        
        limit = limit_config["limit"]
        window = limit_config["window"]
        
        # Use user-specific limits if authenticated
        if hasattr(request.state, "user"):
            user = request.state.user
            if user.is_admin:
                # Admins get higher limits
                limit = limit * 5
            key = f"rate_limit:{endpoint}:user:{user.id}"
        else:
            key = f"rate_limit:{endpoint}:ip:{client_ip}"
        
        current_time = int(time.time())
        
        try:
            # Use sliding window algorithm
            pipe = self.cache.pipeline()
            
            # Remove old entries
            pipe.zremrangebyscore(key, 0, current_time - window)
            
            # Count current requests
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(current_time): current_time})
            
            # Set expiration
            pipe.expire(key, window * 2)
            
            results = await pipe.execute()
            current_count = results[1]
            
            if current_count >= limit:
                # Calculate retry after
                oldest_request = await self.cache.zrange(key, 0, 0, withscores=True)
                if oldest_request:
                    oldest_time = int(oldest_request[0][1])
                    retry_after = max(1, oldest_time + window - current_time)
                    return True, retry_after
            
            return False, 0
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # Fail open - allow request if Redis is down
            return False, 0
    
    async def _record_request(self, client_ip: str, endpoint: str):
        """Record request for rate limiting purposes."""
        # This is handled in the check methods above
        pass
    
    async def _add_rate_limit_headers(self, response, client_ip: str, endpoint: str):
        """Add rate limit headers to response."""
        try:
            limit_config = self.endpoint_limits.get(endpoint, {
                "limit": self.default_limit,
                "window": self.default_window
            })
            
            key = f"rate_limit:{endpoint}:ip:{client_ip}"
            current_time = int(time.time())
            window = limit_config["window"]
            
            # Get current usage
            current_count = await self.cache.zcard(key)
            remaining = max(0, limit_config["limit"] - current_count)
            
            # Calculate reset time
            oldest_request = await self.cache.zrange(key, 0, 0, withscores=True)
            if oldest_request:
                oldest_time = int(oldest_request[0][1])
                reset_time = oldest_time + window
            else:
                reset_time = current_time + window
            
            # Add headers
            response.headers["X-RateLimit-Limit"] = str(limit_config["limit"])
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_time)
            response.headers["X-RateLimit-Window"] = str(window)
            
        except Exception as e:
            logger.error(f"Error adding rate limit headers: {e}")
    
    def _create_rate_limit_response(self, limit: int, window: int, retry_after: int) -> JSONResponse:
        """Create rate limit exceeded response."""
        error = RateLimitError(limit, window, retry_after)
        
        return JSONResponse(
            status_code=429,
            content={"error": error.to_dict()},
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Window": str(window)
            }
        )