"""
Custom exceptions for the Evently Booking Platform.
"""

from typing import Any, Dict, Optional, List
from enum import Enum


class ErrorCode(str, Enum):
    """Standard error codes for the platform."""
    
    # General errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    
    # Business logic errors
    INSUFFICIENT_CAPACITY = "INSUFFICIENT_CAPACITY"
    BOOKING_EXPIRED = "BOOKING_EXPIRED"
    INVALID_BOOKING_STATE = "INVALID_BOOKING_STATE"
    EVENT_HAS_BOOKINGS = "EVENT_HAS_BOOKINGS"
    SEAT_NOT_AVAILABLE = "SEAT_NOT_AVAILABLE"
    SEAT_ALREADY_BOOKED = "SEAT_ALREADY_BOOKED"
    SEAT_HOLD_EXPIRED = "SEAT_HOLD_EXPIRED"
    
    # Concurrency errors
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    OPTIMISTIC_LOCK_FAILURE = "OPTIMISTIC_LOCK_FAILURE"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    
    # External service errors
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    PAYMENT_SERVICE_ERROR = "PAYMENT_SERVICE_ERROR"
    EMAIL_SERVICE_ERROR = "EMAIL_SERVICE_ERROR"
    CACHE_SERVICE_ERROR = "CACHE_SERVICE_ERROR"


class EventlyError(Exception):
    """Base exception class for Evently platform."""
    
    def __init__(
        self, 
        message: str, 
        error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        details: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[str]] = None,
        retry_after: Optional[int] = None
    ):
        """Initialize the exception with comprehensive error information."""
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.suggestions = suggestions or []
        self.retry_after = retry_after
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        result = {
            "error_code": self.error_code.value,
            "message": self.message,
        }
        
        if self.details:
            result["details"] = self.details
        
        if self.suggestions:
            result["suggestions"] = self.suggestions
        
        if self.retry_after:
            result["retry_after"] = self.retry_after
        
        return result


class ValidationError(EventlyError):
    """Exception raised for validation errors."""
    
    def __init__(self, message: str, field_errors: Optional[Dict[str, List[str]]] = None, **kwargs):
        super().__init__(
            message, 
            error_code=ErrorCode.VALIDATION_ERROR,
            details={"field_errors": field_errors} if field_errors else None,
            **kwargs
        )
        self.field_errors = field_errors or {}


class NotFoundError(EventlyError):
    """Base exception for resource not found errors."""
    
    def __init__(self, message: str, resource_type: Optional[str] = None, resource_id: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.NOT_FOUND,
            details={"resource_type": resource_type, "resource_id": resource_id} if resource_type else None,
            **kwargs
        )


class EventNotFoundError(NotFoundError):
    """Exception raised when an event is not found."""
    
    def __init__(self, event_id: str, **kwargs):
        super().__init__(
            f"Event {event_id} not found",
            resource_type="event",
            resource_id=event_id,
            suggestions=["Check the event ID", "Browse available events"],
            **kwargs
        )


class UserNotFoundError(NotFoundError):
    """Exception raised when a user is not found."""
    
    def __init__(self, user_id: str, **kwargs):
        super().__init__(
            f"User {user_id} not found",
            resource_type="user",
            resource_id=user_id,
            **kwargs
        )


class BookingNotFoundError(NotFoundError):
    """Exception raised when a booking is not found."""
    
    def __init__(self, booking_id: str, **kwargs):
        super().__init__(
            f"Booking {booking_id} not found",
            resource_type="booking",
            resource_id=booking_id,
            suggestions=["Check the booking ID", "View your booking history"],
            **kwargs
        )


class AuthenticationError(EventlyError):
    """Exception raised for authentication failures."""
    
    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.UNAUTHORIZED,
            suggestions=["Check your credentials", "Login again"],
            **kwargs
        )


class AuthorizationError(EventlyError):
    """Exception raised for authorization failures."""
    
    def __init__(self, message: str = "Access denied", required_permission: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.FORBIDDEN,
            details={"required_permission": required_permission} if required_permission else None,
            suggestions=["Contact an administrator for access"],
            **kwargs
        )


class BusinessLogicError(EventlyError):
    """Base exception for business logic violations."""
    pass


class EventHasBookingsError(BusinessLogicError):
    """Exception raised when trying to delete an event with bookings."""
    
    def __init__(self, event_id: str, booking_count: int, **kwargs):
        super().__init__(
            f"Cannot delete event {event_id} with {booking_count} active bookings",
            error_code=ErrorCode.EVENT_HAS_BOOKINGS,
            details={"event_id": event_id, "booking_count": booking_count},
            suggestions=["Cancel all bookings first", "Archive the event instead"],
            **kwargs
        )


class InsufficientCapacityError(BusinessLogicError):
    """Exception raised when event capacity is insufficient."""
    
    def __init__(self, requested: int, available: int, event_id: Optional[str] = None, **kwargs):
        super().__init__(
            f"Insufficient capacity: requested {requested}, available {available}",
            error_code=ErrorCode.INSUFFICIENT_CAPACITY,
            details={"requested": requested, "available": available, "event_id": event_id},
            suggestions=["Try booking fewer tickets", "Join the waitlist", "Check similar events"],
            **kwargs
        )


class BookingExpiredError(BusinessLogicError):
    """Exception raised when a booking has expired."""
    
    def __init__(self, booking_id: str, **kwargs):
        super().__init__(
            f"Booking {booking_id} has expired",
            error_code=ErrorCode.BOOKING_EXPIRED,
            details={"booking_id": booking_id},
            suggestions=["Create a new booking", "Complete payment faster next time"],
            **kwargs
        )


class InvalidBookingStateError(BusinessLogicError):
    """Exception raised when booking is in invalid state for operation."""
    
    def __init__(self, booking_id: str, current_state: str, required_state: str, **kwargs):
        super().__init__(
            f"Booking {booking_id} is in {current_state} state, required {required_state}",
            error_code=ErrorCode.INVALID_BOOKING_STATE,
            details={"booking_id": booking_id, "current_state": current_state, "required_state": required_state},
            **kwargs
        )


class ConcurrencyError(EventlyError):
    """Exception raised for concurrency-related issues."""
    
    def __init__(self, message: str, retry_after: int = 1, **kwargs):
        super().__init__(
            message,
            error_code=ErrorCode.CONCURRENCY_CONFLICT,
            retry_after=retry_after,
            suggestions=["Please try again", "Wait a moment and retry"],
            **kwargs
        )


class OptimisticLockError(ConcurrencyError):
    """Exception raised when optimistic locking fails."""
    
    def __init__(self, resource_type: str, resource_id: str, **kwargs):
        super().__init__(
            f"{resource_type} {resource_id} was modified by another transaction",
            details={"resource_type": resource_type, "resource_id": resource_id},
            error_code=ErrorCode.OPTIMISTIC_LOCK_FAILURE,
            **kwargs
        )


class RateLimitError(EventlyError):
    """Exception raised when rate limit is exceeded."""
    
    def __init__(self, limit: int, window: int, retry_after: int, **kwargs):
        super().__init__(
            f"Rate limit exceeded: {limit} requests per {window} seconds",
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            details={"limit": limit, "window": window},
            retry_after=retry_after,
            suggestions=[f"Wait {retry_after} seconds before retrying"],
            **kwargs
        )


class SeatNotFoundError(NotFoundError):
    """Exception raised when a seat is not found."""
    
    def __init__(self, seat_id: str, **kwargs):
        super().__init__(
            f"Seat {seat_id} not found",
            resource_type="seat",
            resource_id=seat_id,
            **kwargs
        )


class SeatNotAvailableError(BusinessLogicError):
    """Exception raised when a seat is not available for booking."""
    
    def __init__(self, seat_id: str, current_status: str, **kwargs):
        super().__init__(
            f"Seat {seat_id} is not available (status: {current_status})",
            error_code=ErrorCode.SEAT_NOT_AVAILABLE,
            details={"seat_id": seat_id, "current_status": current_status},
            suggestions=["Choose a different seat", "Check seat availability"],
            **kwargs
        )


class SeatHoldExpiredError(BusinessLogicError):
    """Exception raised when a seat hold has expired."""
    
    def __init__(self, seat_id: str, **kwargs):
        super().__init__(
            f"Seat hold for {seat_id} has expired",
            error_code=ErrorCode.SEAT_HOLD_EXPIRED,
            details={"seat_id": seat_id},
            suggestions=["Select the seat again", "Complete booking faster"],
            **kwargs
        )


class SeatAlreadyBookedError(BusinessLogicError):
    """Exception raised when trying to book an already booked seat."""
    
    def __init__(self, seat_id: str, **kwargs):
        super().__init__(
            f"Seat {seat_id} is already booked",
            error_code=ErrorCode.SEAT_ALREADY_BOOKED,
            details={"seat_id": seat_id},
            suggestions=["Choose a different seat", "Refresh seat availability"],
            **kwargs
        )


class ExternalServiceError(EventlyError):
    """Exception raised for external service failures."""
    
    def __init__(self, service_name: str, message: str, status_code: Optional[int] = None, **kwargs):
        super().__init__(
            f"{service_name} service error: {message}",
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            details={"service_name": service_name, "status_code": status_code},
            suggestions=["Try again later", "Contact support if problem persists"],
            **kwargs
        )


class PaymentServiceError(ExternalServiceError):
    """Exception raised for payment service failures."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            "payment",
            message,
            error_code=ErrorCode.PAYMENT_SERVICE_ERROR,
            **kwargs
        )


class EmailServiceError(ExternalServiceError):
    """Exception raised for email service failures."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            "email",
            message,
            error_code=ErrorCode.EMAIL_SERVICE_ERROR,
            **kwargs
        )


class CacheServiceError(ExternalServiceError):
    """Exception raised for cache service failures."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            "cache",
            message,
            error_code=ErrorCode.CACHE_SERVICE_ERROR,
            **kwargs
        )