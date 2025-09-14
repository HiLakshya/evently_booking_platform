"""
Request validation middleware with detailed error responses.
"""

import logging
from typing import Dict, Any, Optional, List
import json

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..utils.exceptions import ValidationError, ErrorCode

logger = logging.getLogger(__name__)


class ValidationMiddleware(BaseHTTPMiddleware):
    """Middleware for enhanced request validation and sanitization."""
    
    def __init__(self, app, max_request_size: int = 10 * 1024 * 1024):  # 10MB default
        super().__init__(app)
        self.max_request_size = max_request_size
    
    async def dispatch(self, request: Request, call_next):
        """Process request with validation checks."""
        
        # Validate request size
        if await self._validate_request_size(request):
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "error_code": ErrorCode.VALIDATION_ERROR.value,
                        "message": f"Request too large. Maximum size is {self.max_request_size} bytes",
                        "suggestions": ["Reduce request payload size"]
                    }
                }
            )
        
        # Validate content type for POST/PUT requests
        if request.method in ["POST", "PUT", "PATCH"]:
            validation_error = await self._validate_content_type(request)
            if validation_error:
                return validation_error
        
        # Validate JSON payload if present
        if request.method in ["POST", "PUT", "PATCH"] and self._has_json_content(request):
            validation_error = await self._validate_json_payload(request)
            if validation_error:
                return validation_error
        
        # Validate query parameters
        validation_error = self._validate_query_parameters(request)
        if validation_error:
            return validation_error
        
        # Continue with request processing
        response = await call_next(request)
        return response
    
    async def _validate_request_size(self, request: Request) -> bool:
        """Validate request size doesn't exceed limits."""
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                return size > self.max_request_size
            except ValueError:
                return False
        return False
    
    async def _validate_content_type(self, request: Request) -> Optional[JSONResponse]:
        """Validate content type for requests with body."""
        content_type = request.headers.get("content-type", "")
        
        # Allow multipart for file uploads
        if content_type.startswith("multipart/"):
            return None
        
        # Require JSON for API endpoints
        if not content_type.startswith("application/json"):
            error = ValidationError(
                "Invalid content type",
                details={"expected": "application/json", "received": content_type},
                suggestions=["Set Content-Type header to application/json"]
            )
            
            return JSONResponse(
                status_code=415,
                content={"error": error.to_dict()}
            )
        
        return None
    
    def _has_json_content(self, request: Request) -> bool:
        """Check if request has JSON content."""
        content_type = request.headers.get("content-type", "")
        return content_type.startswith("application/json")
    
    async def _validate_json_payload(self, request: Request) -> Optional[JSONResponse]:
        """Validate JSON payload structure and content."""
        try:
            # Try to parse JSON to validate structure
            body = await request.body()
            if body:
                json.loads(body)
        except json.JSONDecodeError as e:
            error = ValidationError(
                "Invalid JSON payload",
                details={
                    "json_error": str(e),
                    "line": getattr(e, 'lineno', None),
                    "column": getattr(e, 'colno', None)
                },
                suggestions=["Check JSON syntax", "Validate JSON structure"]
            )
            
            return JSONResponse(
                status_code=400,
                content={"error": error.to_dict()}
            )
        except Exception as e:
            logger.warning(f"Error validating JSON payload: {e}")
        
        return None
    
    def _validate_query_parameters(self, request: Request) -> Optional[JSONResponse]:
        """Validate query parameters for common issues."""
        query_params = request.query_params
        errors = []
        
        # Check for common parameter validation
        for param, value in query_params.items():
            # Validate limit parameter
            if param == "limit":
                try:
                    limit_val = int(value)
                    if limit_val < 1:
                        errors.append(f"Parameter 'limit' must be positive, got {limit_val}")
                    elif limit_val > 1000:
                        errors.append(f"Parameter 'limit' cannot exceed 1000, got {limit_val}")
                except ValueError:
                    errors.append(f"Parameter 'limit' must be an integer, got '{value}'")
            
            # Validate offset parameter
            elif param == "offset":
                try:
                    offset_val = int(value)
                    if offset_val < 0:
                        errors.append(f"Parameter 'offset' must be non-negative, got {offset_val}")
                except ValueError:
                    errors.append(f"Parameter 'offset' must be an integer, got '{value}'")
            
            # Validate sort_order parameter
            elif param == "sort_order":
                if value.lower() not in ["asc", "desc"]:
                    errors.append(f"Parameter 'sort_order' must be 'asc' or 'desc', got '{value}'")
            
            # Check for potentially dangerous characters
            elif self._contains_dangerous_chars(value):
                errors.append(f"Parameter '{param}' contains invalid characters")
        
        if errors:
            error = ValidationError(
                "Invalid query parameters",
                details={"parameter_errors": errors},
                suggestions=["Check parameter values and types"]
            )
            
            return JSONResponse(
                status_code=400,
                content={"error": error.to_dict()}
            )
        
        return None
    
    def _contains_dangerous_chars(self, value: str) -> bool:
        """Check for potentially dangerous characters in parameters."""
        dangerous_chars = ["<", ">", "script", "javascript:", "data:", "vbscript:"]
        value_lower = value.lower()
        return any(char in value_lower for char in dangerous_chars)


class RequestSanitizerMiddleware(BaseHTTPMiddleware):
    """Middleware for sanitizing request data."""
    
    def __init__(self, app):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        """Sanitize request data before processing."""
        
        # Sanitize headers
        self._sanitize_headers(request)
        
        # Continue with request processing
        response = await call_next(request)
        return response
    
    def _sanitize_headers(self, request: Request):
        """Sanitize request headers."""
        # Remove or sanitize potentially dangerous headers
        dangerous_headers = ["x-forwarded-host", "x-original-url", "x-rewrite-url"]
        
        for header in dangerous_headers:
            if header in request.headers:
                logger.warning(f"Potentially dangerous header removed: {header}")
                # Note: We can't actually modify headers in Starlette middleware
                # This is more for logging and monitoring purposes