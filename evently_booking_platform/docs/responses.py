"""
Standard API response examples for documentation.
"""

from typing import Dict, Any
from fastapi import status

# Common Error Responses
ERROR_RESPONSES: Dict[int, Dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        "description": "Bad Request - Invalid input data",
        "content": {
            "application/json": {
                "examples": {
                    "validation_error": {
                        "summary": "Validation Error",
                        "value": {
                            "error": {
                                "code": "VALIDATION_ERROR",
                                "message": "Invalid input data",
                                "details": {
                                    "field": "email",
                                    "value": "invalid-email",
                                    "constraint": "must be a valid email address"
                                }
                            }
                        }
                    },
                    "capacity_exceeded": {
                        "summary": "Event Capacity Exceeded",
                        "value": {
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
                        }
                    }
                }
            }
        }
    },
    status.HTTP_401_UNAUTHORIZED: {
        "description": "Unauthorized - Authentication required",
        "content": {
            "application/json": {
                "examples": {
                    "missing_token": {
                        "summary": "Missing Authentication Token",
                        "value": {
                            "error": {
                                "code": "AUTHENTICATION_REQUIRED",
                                "message": "Authentication required to access this resource",
                                "suggestions": [
                                    "Include Authorization header with valid JWT token",
                                    "Login to get an access token"
                                ]
                            }
                        }
                    },
                    "invalid_token": {
                        "summary": "Invalid Authentication Token",
                        "value": {
                            "error": {
                                "code": "INVALID_TOKEN",
                                "message": "Invalid or expired authentication token",
                                "suggestions": [
                                    "Login again to get a new access token",
                                    "Check token format and expiration"
                                ]
                            }
                        }
                    }
                }
            }
        }
    },
    status.HTTP_403_FORBIDDEN: {
        "description": "Forbidden - Insufficient permissions",
        "content": {
            "application/json": {
                "examples": {
                    "admin_required": {
                        "summary": "Admin Access Required",
                        "value": {
                            "error": {
                                "code": "INSUFFICIENT_PERMISSIONS",
                                "message": "Admin privileges required to access this resource",
                                "details": {
                                    "required_role": "admin",
                                    "current_role": "user"
                                }
                            }
                        }
                    }
                }
            }
        }
    },
    status.HTTP_404_NOT_FOUND: {
        "description": "Not Found - Resource does not exist",
        "content": {
            "application/json": {
                "examples": {
                    "event_not_found": {
                        "summary": "Event Not Found",
                        "value": {
                            "error": {
                                "code": "EVENT_NOT_FOUND",
                                "message": "Event not found",
                                "details": {
                                    "event_id": "123e4567-e89b-12d3-a456-426614174000"
                                },
                                "suggestions": [
                                    "Check the event ID",
                                    "Browse available events"
                                ]
                            }
                        }
                    },
                    "booking_not_found": {
                        "summary": "Booking Not Found",
                        "value": {
                            "error": {
                                "code": "BOOKING_NOT_FOUND",
                                "message": "Booking not found",
                                "details": {
                                    "booking_id": "123e4567-e89b-12d3-a456-426614174000"
                                }
                            }
                        }
                    }
                }
            }
        }
    },
    status.HTTP_409_CONFLICT: {
        "description": "Conflict - Resource conflict or concurrency issue",
        "content": {
            "application/json": {
                "examples": {
                    "seat_already_taken": {
                        "summary": "Seat Already Taken",
                        "value": {
                            "error": {
                                "code": "SEAT_ALREADY_TAKEN",
                                "message": "Selected seat is no longer available",
                                "details": {
                                    "seat_id": "seat-123e4567-e89b-12d3-a456-426614174001",
                                    "section": "VIP",
                                    "row": "A",
                                    "number": "1"
                                },
                                "suggestions": [
                                    "Select different seats",
                                    "Refresh seat map for current availability"
                                ]
                            }
                        }
                    },
                    "event_has_bookings": {
                        "summary": "Event Has Active Bookings",
                        "value": {
                            "error": {
                                "code": "EVENT_HAS_BOOKINGS",
                                "message": "Cannot delete event with active bookings",
                                "details": {
                                    "event_id": "123e4567-e89b-12d3-a456-426614174000",
                                    "active_bookings": 25
                                },
                                "suggestions": [
                                    "Cancel all bookings first",
                                    "Deactivate event instead of deleting"
                                ]
                            }
                        }
                    }
                }
            }
        }
    },
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "description": "Too Many Requests - Rate limit exceeded",
        "content": {
            "application/json": {
                "examples": {
                    "rate_limit_exceeded": {
                        "summary": "Rate Limit Exceeded",
                        "value": {
                            "error": {
                                "code": "RATE_LIMIT_EXCEEDED",
                                "message": "Too many requests. Please try again later.",
                                "details": {
                                    "limit": 100,
                                    "window": "1 minute",
                                    "retry_after": 30
                                },
                                "suggestions": [
                                    "Wait before making more requests",
                                    "Implement exponential backoff"
                                ]
                            }
                        }
                    }
                }
            }
        }
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "description": "Internal Server Error - Unexpected server error",
        "content": {
            "application/json": {
                "examples": {
                    "server_error": {
                        "summary": "Internal Server Error",
                        "value": {
                            "error": {
                                "code": "INTERNAL_SERVER_ERROR",
                                "message": "An unexpected error occurred. Please try again later.",
                                "details": {
                                    "request_id": "req_123456789"
                                },
                                "suggestions": [
                                    "Try the request again",
                                    "Contact support if the problem persists"
                                ]
                            }
                        }
                    }
                }
            }
        }
    }
}

# Success Response Examples
SUCCESS_RESPONSES: Dict[str, Dict[str, Any]] = {
    "event_created": {
        "summary": "Event Created Successfully",
        "value": {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "name": "Summer Music Festival 2024",
            "description": "Join us for an unforgettable night of music",
            "venue": "Central Park Amphitheater",
            "event_date": "2024-07-15T19:00:00Z",
            "total_capacity": 5000,
            "available_capacity": 5000,
            "price": 89.99,
            "has_seat_selection": True,
            "is_active": True,
            "version": 1,
            "created_at": "2024-01-01T12:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
            "is_sold_out": False,
            "capacity_utilization": 0.0
        }
    },
    "booking_created": {
        "summary": "Booking Created Successfully",
        "value": {
            "id": "booking-123e4567-e89b-12d3-a456-426614174000",
            "event_id": "123e4567-e89b-12d3-a456-426614174000",
            "user_id": "user-123e4567-e89b-12d3-a456-426614174000",
            "quantity": 2,
            "total_amount": 179.98,
            "status": "confirmed",
            "created_at": "2024-01-01T12:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
            "expires_at": None,
            "seats": [
                {
                    "id": "seat-123e4567-e89b-12d3-a456-426614174001",
                    "section": "VIP",
                    "row": "A",
                    "number": "1",
                    "price": 89.99
                },
                {
                    "id": "seat-123e4567-e89b-12d3-a456-426614174002",
                    "section": "VIP",
                    "row": "A",
                    "number": "2",
                    "price": 89.99
                }
            ]
        }
    },
    "user_registered": {
        "summary": "User Registered Successfully",
        "value": {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer",
            "expires_in": 3600,
            "user": {
                "id": "user-123e4567-e89b-12d3-a456-426614174000",
                "email": "john.doe@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "is_admin": False,
                "is_active": True
            }
        }
    }
}