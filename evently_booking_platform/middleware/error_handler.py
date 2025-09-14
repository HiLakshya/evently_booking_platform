"""
Comprehensive error handling middleware for the Evently Booking Platform.
"""

import logging
import traceback
from typing import Dict, Any, Optional
from uuid import uuid4

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.exc import IntegrityError, OperationalError, TimeoutError as SQLTimeoutError
from pydantic import ValidationError as PydanticValidationError

from ..utils.exceptions import (
    EventlyError,
    ErrorCode,
    ValidationError,
    NotFoundError,
    AuthenticationError,
    AuthorizationError,
    BusinessLogicError,
    ConcurrencyError,
    ExternalServiceError,
    RateLimitError
)

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive error handling and response formatting."""
    
    def __init__(self, app, debug: bool = False):
        super().__init__(app)
        self.debug = debug
    
    async def dispatch(self, request: Request, call_next):
        """Process request and handle any exceptions."""
        error_id = str(uuid4())
        
        try:
            response = await call_next(request)
            return response
            
        except Exception as exc:
            return await self._handle_exception(request, exc, error_id)
    
    async def _handle_exception(self, request: Request, exc: Exception, error_id: str) -> JSONResponse:
        """Handle different types of exceptions and return appropriate responses."""
        
        # Log the error with context
        await self._log_error(request, exc, error_id)
        
        # Handle specific exception types
        if isinstance(exc, EventlyError):
            return self._handle_evently_error(exc, error_id)
        elif isinstance(exc, PydanticValidationError):
            return self._handle_validation_error(exc, error_id)
        elif isinstance(exc, IntegrityError):
            return self._handle_integrity_error(exc, error_id)
        elif isinstance(exc, (OperationalError, SQLTimeoutError)):
            return self._handle_database_error(exc, error_id)
        else:
            return self._handle_unexpected_error(exc, error_id)
    
    def _handle_evently_error(self, exc: EventlyError, error_id: str) -> JSONResponse:
        """Handle custom Evently platform errors."""
        status_code = self._get_status_code_for_error(exc)
        
        response_data = {
            "error": exc.to_dict(),
            "error_id": error_id,
            "timestamp": self._get_timestamp()
        }
        
        # Add retry-after header if specified
        headers = {}
        if exc.retry_after:
            headers["Retry-After"] = str(exc.retry_after)
        
        return JSONResponse(
            status_code=status_code,
            content=response_data,
            headers=headers
        )
    
    def _handle_validation_error(self, exc: PydanticValidationError, error_id: str) -> JSONResponse:
        """Handle Pydantic validation errors."""
        field_errors = {}
        
        for error in exc.errors():
            field_path = ".".join(str(loc) for loc in error["loc"])
            if field_path not in field_errors:
                field_errors[field_path] = []
            field_errors[field_path].append(error["msg"])
        
        validation_error = ValidationError(
            "Request validation failed",
            field_errors=field_errors
        )
        
        response_data = {
            "error": validation_error.to_dict(),
            "error_id": error_id,
            "timestamp": self._get_timestamp()
        }
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=response_data
        )
    
    def _handle_integrity_error(self, exc: IntegrityError, error_id: str) -> JSONResponse:
        """Handle database integrity constraint violations."""
        # Parse common integrity errors
        error_message = str(exc.orig) if hasattr(exc, 'orig') else str(exc)
        
        if "unique constraint" in error_message.lower():
            evently_error = ValidationError(
                "A record with this information already exists",
                details={"constraint_type": "unique"}
            )
        elif "foreign key constraint" in error_message.lower():
            evently_error = ValidationError(
                "Referenced resource does not exist",
                details={"constraint_type": "foreign_key"}
            )
        elif "not null constraint" in error_message.lower():
            evently_error = ValidationError(
                "Required field is missing",
                details={"constraint_type": "not_null"}
            )
        else:
            evently_error = ValidationError(
                "Data integrity constraint violation",
                details={"constraint_type": "unknown"}
            )
        
        response_data = {
            "error": evently_error.to_dict(),
            "error_id": error_id,
            "timestamp": self._get_timestamp()
        }
        
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=response_data
        )
    
    def _handle_database_error(self, exc: Exception, error_id: str) -> JSONResponse:
        """Handle database connection and operational errors."""
        evently_error = ExternalServiceError(
            "database",
            "Database service temporarily unavailable",
            details={"error_type": type(exc).__name__}
        )
        
        response_data = {
            "error": evently_error.to_dict(),
            "error_id": error_id,
            "timestamp": self._get_timestamp()
        }
        
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_data,
            headers={"Retry-After": "30"}
        )
    
    def _handle_unexpected_error(self, exc: Exception, error_id: str) -> JSONResponse:
        """Handle unexpected errors."""
        evently_error = EventlyError(
            "An unexpected error occurred",
            error_code=ErrorCode.INTERNAL_ERROR,
            details={"error_type": type(exc).__name__} if self.debug else None
        )
        
        response_data = {
            "error": evently_error.to_dict(),
            "error_id": error_id,
            "timestamp": self._get_timestamp()
        }
        
        # Include stack trace in debug mode
        if self.debug:
            response_data["debug"] = {
                "exception": str(exc),
                "traceback": traceback.format_exc()
            }
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_data
        )
    
    def _get_status_code_for_error(self, exc: EventlyError) -> int:
        """Map error codes to HTTP status codes."""
        status_map = {
            ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
            ErrorCode.UNAUTHORIZED: status.HTTP_401_UNAUTHORIZED,
            ErrorCode.FORBIDDEN: status.HTTP_403_FORBIDDEN,
            ErrorCode.INSUFFICIENT_CAPACITY: status.HTTP_409_CONFLICT,
            ErrorCode.BOOKING_EXPIRED: status.HTTP_410_GONE,
            ErrorCode.INVALID_BOOKING_STATE: status.HTTP_400_BAD_REQUEST,
            ErrorCode.EVENT_HAS_BOOKINGS: status.HTTP_409_CONFLICT,
            ErrorCode.SEAT_NOT_AVAILABLE: status.HTTP_409_CONFLICT,
            ErrorCode.SEAT_ALREADY_BOOKED: status.HTTP_409_CONFLICT,
            ErrorCode.SEAT_HOLD_EXPIRED: status.HTTP_410_GONE,
            ErrorCode.CONCURRENCY_CONFLICT: status.HTTP_409_CONFLICT,
            ErrorCode.OPTIMISTIC_LOCK_FAILURE: status.HTTP_409_CONFLICT,
            ErrorCode.RATE_LIMIT_EXCEEDED: status.HTTP_429_TOO_MANY_REQUESTS,
            ErrorCode.EXTERNAL_SERVICE_ERROR: status.HTTP_503_SERVICE_UNAVAILABLE,
            ErrorCode.PAYMENT_SERVICE_ERROR: status.HTTP_502_BAD_GATEWAY,
            ErrorCode.EMAIL_SERVICE_ERROR: status.HTTP_503_SERVICE_UNAVAILABLE,
            ErrorCode.CACHE_SERVICE_ERROR: status.HTTP_503_SERVICE_UNAVAILABLE,
        }
        
        return status_map.get(exc.error_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    async def _log_error(self, request: Request, exc: Exception, error_id: str):
        """Log error with comprehensive context."""
        # Extract request information
        request_info = {
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }
        
        # Extract user information if available
        user_info = {}
        if hasattr(request.state, "user"):
            user_info = {
                "user_id": str(request.state.user.id),
                "email": request.state.user.email,
                "is_admin": request.state.user.is_admin
            }
        
        # Log based on error severity
        if isinstance(exc, EventlyError):
            if isinstance(exc, (ValidationError, NotFoundError)):
                logger.warning(
                    f"Client error [{error_id}]: {exc.message}",
                    extra={
                        "error_id": error_id,
                        "error_code": exc.error_code.value,
                        "request": request_info,
                        "user": user_info,
                        "details": exc.details
                    }
                )
            elif isinstance(exc, (ConcurrencyError, ExternalServiceError)):
                logger.error(
                    f"System error [{error_id}]: {exc.message}",
                    extra={
                        "error_id": error_id,
                        "error_code": exc.error_code.value,
                        "request": request_info,
                        "user": user_info,
                        "details": exc.details
                    }
                )
            else:
                logger.error(
                    f"Business error [{error_id}]: {exc.message}",
                    extra={
                        "error_id": error_id,
                        "error_code": exc.error_code.value,
                        "request": request_info,
                        "user": user_info,
                        "details": exc.details
                    }
                )
        else:
            logger.error(
                f"Unexpected error [{error_id}]: {str(exc)}",
                extra={
                    "error_id": error_id,
                    "error_type": type(exc).__name__,
                    "request": request_info,
                    "user": user_info,
                    "traceback": traceback.format_exc()
                }
            )
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"