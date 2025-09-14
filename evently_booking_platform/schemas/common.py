"""
Common schemas for API responses and error handling.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Schema for detailed error information."""
    
    code: str = Field(..., description="Error code for programmatic handling")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error context")
    suggestions: Optional[List[str]] = Field(None, description="Helpful suggestions for resolving the error")


class ErrorResponse(BaseModel):
    """Schema for API error responses."""
    
    error: ErrorDetail
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "error": {
                        "code": "BOOKING_CAPACITY_EXCEEDED",
                        "message": "Event is sold out",
                        "details": {
                            "event_id": "123e4567-e89b-12d3-a456-426614174000",
                            "requested_quantity": 2,
                            "available_capacity": 0,
                            "waitlist_available": True
                        },
                        "suggestions": [
                            "Join the waitlist for this event",
                            "Check similar events"
                        ]
                    }
                },
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid input data",
                        "details": {
                            "field": "email",
                            "value": "invalid-email",
                            "constraint": "must be a valid email address"
                        }
                    }
                },
                {
                    "error": {
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": "Authentication required to access this resource",
                        "suggestions": [
                            "Include Authorization header with valid JWT token",
                            "Login to get an access token"
                        ]
                    }
                }
            ]
        }


class SuccessResponse(BaseModel):
    """Schema for simple success responses."""
    
    message: str = Field(..., description="Success message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional response data")


class PaginationInfo(BaseModel):
    """Schema for pagination information."""
    
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")


class HealthStatus(BaseModel):
    """Schema for health check responses."""
    
    status: str = Field(..., description="Overall health status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    timestamp: str = Field(..., description="Health check timestamp")
    dependencies: Optional[Dict[str, Dict[str, Any]]] = Field(
        None, 
        description="Status of service dependencies"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "service": "evently-booking-platform",
                "version": "1.0.0",
                "timestamp": "2024-01-01T12:00:00Z",
                "dependencies": {
                    "database": {
                        "status": "healthy",
                        "response_time_ms": 15,
                        "connection_pool": {
                            "active": 5,
                            "idle": 10,
                            "max": 20
                        }
                    },
                    "redis": {
                        "status": "healthy",
                        "response_time_ms": 2,
                        "memory_usage": "45MB"
                    }
                }
            }
        }


class MetricsResponse(BaseModel):
    """Schema for metrics responses."""
    
    circuit_breakers: Dict[str, Any] = Field(..., description="Circuit breaker statistics")
    middleware: Dict[str, Any] = Field(..., description="Middleware performance metrics")
    timestamp: str = Field(..., description="Metrics collection timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "circuit_breakers": {
                    "database": {
                        "state": "closed",
                        "failure_count": 0,
                        "success_count": 1250,
                        "last_failure": None
                    }
                },
                "middleware": {
                    "request_count": 1500,
                    "average_response_time": 125.5,
                    "error_rate": 0.02
                },
                "timestamp": "2024-01-01T12:00:00Z"
            }
        }