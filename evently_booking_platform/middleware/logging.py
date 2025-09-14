"""
Comprehensive logging middleware for request/response tracking and monitoring.
"""

import logging
import time
import json
import contextvars
from typing import Dict, Any, Optional
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Context variable for request ID
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default='no-request-id')


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive request/response logging and monitoring."""
    
    def __init__(
        self,
        app,
        log_requests: bool = True,
        log_responses: bool = True,
        log_request_body: bool = False,
        log_response_body: bool = False,
        sensitive_headers: Optional[list] = None
    ):
        super().__init__(app)
        self.log_requests = log_requests
        self.log_responses = log_responses
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.sensitive_headers = sensitive_headers or [
            "authorization", "cookie", "x-api-key", "x-auth-token"
        ]
    
    async def dispatch(self, request: Request, call_next):
        """Log request and response with comprehensive context."""
        
        # Generate request ID for tracing
        request_id = str(uuid4())
        request.state.request_id = request_id
        
        # Set request ID in context variable for all loggers to access
        request_id_var.set(request_id)
        
        # Record start time
        start_time = time.time()
        
        # Log incoming request
        if self.log_requests:
            await self._log_request(request, request_id)
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.4f}"
            
            # Log response
            if self.log_responses:
                await self._log_response(request, response, request_id, process_time)
            
            return response
            
        except Exception as exc:
            # Log exception
            process_time = time.time() - start_time
            await self._log_exception(request, exc, request_id, process_time)
            raise
        finally:
            # Clear the context variable
            request_id_var.set('no-request-id')
    
    async def _log_request(self, request: Request, request_id: str):
        """Log incoming request details."""
        
        # Extract basic request info
        request_info = {
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_ip": self._get_client_ip(request),
            "user_agent": request.headers.get("user-agent"),
            "content_type": request.headers.get("content-type"),
            "content_length": request.headers.get("content-length"),
        }
        
        # Add sanitized headers
        request_info["headers"] = self._sanitize_headers(dict(request.headers))
        
        # Add user info if available
        if hasattr(request.state, "user"):
            request_info["user"] = {
                "id": str(request.state.user.id),
                "email": request.state.user.email,
                "is_admin": request.state.user.is_admin
            }
        
        # Add request body if enabled and appropriate
        if self.log_request_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body and len(body) < 10000:  # Limit body size
                    content_type = request.headers.get("content-type", "")
                    if content_type.startswith("application/json"):
                        try:
                            request_info["body"] = json.loads(body)
                        except json.JSONDecodeError:
                            request_info["body"] = body.decode("utf-8", errors="ignore")
                    else:
                        request_info["body"] = f"<{content_type} data>"
            except Exception as e:
                logger.warning(f"Error reading request body: {e}")
        
        # Log with appropriate level
        if request.url.path.startswith("/api/v1/bookings"):
            # High-priority booking operations
            logger.info(f"Booking request: {request.method} {request.url.path}", extra=request_info)
        elif request.url.path in ["/health", "/", "/docs", "/redoc"]:
            # Low-priority health checks
            logger.debug(f"Health check: {request.method} {request.url.path}", extra=request_info)
        else:
            # Standard API requests
            logger.info(f"API request: {request.method} {request.url.path}", extra=request_info)
    
    async def _log_response(self, request: Request, response: Response, request_id: str, process_time: float):
        """Log response details."""
        
        response_info = {
            "request_id": request_id,
            "status_code": response.status_code,
            "process_time": process_time,
            "response_size": response.headers.get("content-length"),
        }
        
        # Add response headers (sanitized)
        response_info["headers"] = self._sanitize_headers(dict(response.headers))
        
        # Add response body if enabled and appropriate
        if self.log_response_body and hasattr(response, "body"):
            try:
                if hasattr(response, "body") and len(response.body) < 10000:
                    content_type = response.headers.get("content-type", "")
                    if content_type.startswith("application/json"):
                        try:
                            response_info["body"] = json.loads(response.body)
                        except (json.JSONDecodeError, AttributeError):
                            pass
            except Exception as e:
                logger.warning(f"Error reading response body: {e}")
        
        # Log with appropriate level based on status code
        if 200 <= response.status_code < 300:
            logger.info(f"Response: {response.status_code} ({process_time:.4f}s)", extra=response_info)
        elif 400 <= response.status_code < 500:
            logger.warning(f"Client error: {response.status_code} ({process_time:.4f}s)", extra=response_info)
        else:
            logger.error(f"Server error: {response.status_code} ({process_time:.4f}s)", extra=response_info)
        
        # Log slow requests
        if process_time > 2.0:
            logger.warning(
                f"Slow request detected: {request.method} {request.url.path} took {process_time:.4f}s",
                extra={
                    "request_id": request_id,
                    "slow_request": True,
                    "process_time": process_time,
                    "threshold": 2.0
                }
            )
    
    async def _log_exception(self, request: Request, exc: Exception, request_id: str, process_time: float):
        """Log exception details."""
        
        exception_info = {
            "request_id": request_id,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "process_time": process_time,
            "method": request.method,
            "url": str(request.url),
        }
        
        # Add user info if available
        if hasattr(request.state, "user"):
            exception_info["user_id"] = str(request.state.user.id)
        
        logger.error(f"Request exception: {type(exc).__name__}", extra=exception_info, exc_info=True)
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request."""
        # Check for forwarded headers
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    def _sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Remove or mask sensitive headers."""
        sanitized = {}
        
        for key, value in headers.items():
            key_lower = key.lower()
            if key_lower in self.sensitive_headers:
                # Mask sensitive headers
                if key_lower == "authorization" and value.startswith("Bearer "):
                    sanitized[key] = f"Bearer ***{value[-4:]}"
                else:
                    sanitized[key] = "***MASKED***"
            else:
                sanitized[key] = value
        
        return sanitized


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware for collecting application metrics."""
    
    def __init__(self, app):
        super().__init__(app)
        self.request_count = {}
        self.response_times = {}
        self.error_count = {}
    
    async def dispatch(self, request: Request, call_next):
        """Collect metrics during request processing."""
        
        start_time = time.time()
        endpoint = self._get_endpoint_pattern(request.url.path)
        
        # Increment request counter
        self.request_count[endpoint] = self.request_count.get(endpoint, 0) + 1
        
        try:
            response = await call_next(request)
            
            # Record response time
            process_time = time.time() - start_time
            if endpoint not in self.response_times:
                self.response_times[endpoint] = []
            self.response_times[endpoint].append(process_time)
            
            # Keep only recent response times (last 1000)
            if len(self.response_times[endpoint]) > 1000:
                self.response_times[endpoint] = self.response_times[endpoint][-1000:]
            
            return response
            
        except Exception as exc:
            # Record error
            error_key = f"{endpoint}:{type(exc).__name__}"
            self.error_count[error_key] = self.error_count.get(error_key, 0) + 1
            raise
    
    def _get_endpoint_pattern(self, path: str) -> str:
        """Extract endpoint pattern for metrics grouping."""
        # Remove IDs and other variable parts
        parts = path.split("/")
        normalized_parts = []
        
        for part in parts:
            # Replace UUIDs and numeric IDs with placeholder
            if self._is_uuid(part) or part.isdigit():
                normalized_parts.append("{id}")
            else:
                normalized_parts.append(part)
        
        return "/".join(normalized_parts)
    
    def _is_uuid(self, value: str) -> bool:
        """Check if string looks like a UUID."""
        try:
            import uuid
            uuid.UUID(value)
            return True
        except ValueError:
            return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics summary."""
        metrics = {
            "request_counts": self.request_count.copy(),
            "error_counts": self.error_count.copy(),
            "response_time_stats": {}
        }
        
        # Calculate response time statistics
        for endpoint, times in self.response_times.items():
            if times:
                metrics["response_time_stats"][endpoint] = {
                    "count": len(times),
                    "avg": sum(times) / len(times),
                    "min": min(times),
                    "max": max(times),
                    "p95": self._percentile(times, 0.95),
                    "p99": self._percentile(times, 0.99)
                }
        
        return metrics
    
    def _percentile(self, data: list, percentile: float) -> float:
        """Calculate percentile of data."""
        if not data:
            return 0.0
        
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile)
        return sorted_data[min(index, len(sorted_data) - 1)]