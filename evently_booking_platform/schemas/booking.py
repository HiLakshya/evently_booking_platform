"""
Pydantic schemas for booking-related API requests and responses.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from ..models.booking import BookingStatus
from ..models.booking_history import BookingAction


class BookingCreateRequest(BaseModel):
    """Schema for creating a new booking."""
    
    event_id: UUID = Field(..., description="ID of the event to book")
    quantity: int = Field(..., ge=1, le=10, description="Number of tickets to book")
    seat_ids: Optional[List[UUID]] = Field(None, description="Optional list of specific seat IDs")
    
    @field_validator('seat_ids')
    @classmethod
    def validate_seat_ids(cls, v, info):
        """Validate that seat_ids length matches quantity if provided."""
        if v is not None and info.data and 'quantity' in info.data:
            if len(v) != info.data['quantity']:
                raise ValueError("Number of seat IDs must match quantity")
        return v


class BookingConfirmRequest(BaseModel):
    """Schema for confirming a booking."""
    
    payment_reference: Optional[str] = Field(None, description="Payment reference from payment processor")


class BookingCancelRequest(BaseModel):
    """Schema for cancelling a booking."""
    
    reason: Optional[str] = Field(None, max_length=500, description="Optional cancellation reason")


class SeatBookingResponse(BaseModel):
    """Schema for seat booking information in responses."""
    
    id: UUID
    seat_id: UUID
    section: str
    row: str
    number: str
    price: Decimal
    
    model_config = {"from_attributes": True}


class BookingResponse(BaseModel):
    """Schema for booking responses."""
    
    id: UUID
    user_id: UUID
    event_id: UUID
    quantity: int
    total_amount: Decimal
    status: BookingStatus
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime]
    
    # Related data
    event_name: Optional[str] = None
    event_date: Optional[datetime] = None
    venue: Optional[str] = None
    seat_bookings: List[SeatBookingResponse] = []
    
    model_config = {"from_attributes": True}


class BookingListResponse(BaseModel):
    """Schema for booking list responses."""
    
    bookings: List[BookingResponse]
    total: int
    limit: int
    offset: int


class BookingStatsResponse(BaseModel):
    """Schema for booking statistics."""
    
    total_bookings: int
    confirmed_bookings: int
    pending_bookings: int
    cancelled_bookings: int
    expired_bookings: int
    total_revenue: Decimal


class BookingErrorResponse(BaseModel):
    """Schema for booking error responses."""
    
    error_code: str
    message: str
    details: Optional[dict] = None
    suggestions: Optional[List[str]] = None


# Request/Response models for different booking operations

class CreateBookingResponse(BaseModel):
    """Response for successful booking creation."""
    
    booking: BookingResponse
    message: str = "Booking created successfully"
    expires_in_minutes: int


class ConfirmBookingResponse(BaseModel):
    """Response for successful booking confirmation."""
    
    booking: BookingResponse
    message: str = "Booking confirmed successfully"


class CancelBookingResponse(BaseModel):
    """Response for successful booking cancellation."""
    
    booking: BookingResponse
    message: str = "Booking cancelled successfully"
    refund_amount: Optional[Decimal] = None


# Validation schemas

class BookingValidationError(BaseModel):
    """Schema for booking validation errors."""
    
    field: str
    message: str
    code: str


class BookingValidationResponse(BaseModel):
    """Schema for booking validation responses."""
    
    valid: bool
    errors: List[BookingValidationError] = []
    warnings: List[str] = []


# Filter schemas

class BookingFilterRequest(BaseModel):
    """Schema for filtering booking requests."""
    
    status: Optional[List[BookingStatus]] = Field(None, description="Filter by booking status")
    event_id: Optional[UUID] = Field(None, description="Filter by event ID")
    date_from: Optional[datetime] = Field(None, description="Filter bookings from this date")
    date_to: Optional[datetime] = Field(None, description="Filter bookings to this date")
    limit: int = Field(50, ge=1, le=100, description="Maximum number of results")
    offset: int = Field(0, ge=0, description="Number of results to skip")


# Booking history schemas

class BookingHistoryResponse(BaseModel):
    """Schema for booking history entries."""
    
    id: UUID
    booking_id: UUID
    action: BookingAction
    details: Optional[str]
    performed_by: Optional[str]
    created_at: datetime
    
    model_config = {"from_attributes": True}


class BookingHistoryListResponse(BaseModel):
    """Schema for booking history list responses."""
    
    history: List[BookingHistoryResponse]
    total: int


# Dashboard schemas

class BookingDashboardStats(BaseModel):
    """Schema for user booking dashboard statistics."""
    
    total_bookings: int
    upcoming_events: int
    past_events: int
    cancelled_bookings: int
    total_spent: Decimal


class BookingDashboardResponse(BaseModel):
    """Schema for user booking dashboard."""
    
    stats: BookingDashboardStats
    upcoming_bookings: List[BookingResponse]
    recent_bookings: List[BookingResponse]


# Receipt schemas

class ReceiptLineItem(BaseModel):
    """Schema for receipt line items."""
    
    description: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal


class BookingReceiptResponse(BaseModel):
    """Schema for booking receipt."""
    
    booking_id: UUID
    booking_reference: str
    event_name: str
    event_date: datetime
    venue: str
    customer_name: str
    customer_email: str
    booking_date: datetime
    line_items: List[ReceiptLineItem]
    subtotal: Decimal
    total_amount: Decimal
    payment_status: str
    seat_details: Optional[List[Dict[str, Any]]] = None


# Enhanced filter schemas

class BookingSearchRequest(BaseModel):
    """Schema for booking search requests."""
    
    query: Optional[str] = Field(None, description="Search query for event name or venue")
    status: Optional[List[BookingStatus]] = Field(None, description="Filter by booking status")
    event_id: Optional[UUID] = Field(None, description="Filter by event ID")
    date_from: Optional[datetime] = Field(None, description="Filter bookings from this date")
    date_to: Optional[datetime] = Field(None, description="Filter bookings to this date")
    min_amount: Optional[Decimal] = Field(None, description="Minimum booking amount")
    max_amount: Optional[Decimal] = Field(None, description="Maximum booking amount")
    sort_by: Optional[str] = Field("created_at", description="Sort field")
    sort_order: Optional[str] = Field("desc", description="Sort order (asc/desc)")
    limit: int = Field(50, ge=1, le=100, description="Maximum number of results")
    offset: int = Field(0, ge=0, description="Number of results to skip")


class BookingCategoryResponse(BaseModel):
    """Schema for categorized booking responses."""
    
    upcoming: List[BookingResponse]
    past: List[BookingResponse]
    cancelled: List[BookingResponse]
    pending: List[BookingResponse]


# Background task schemas

class ExpiredBookingTask(BaseModel):
    """Schema for expired booking background task."""
    
    booking_id: UUID
    expired_at: datetime


class BookingExpirationBatch(BaseModel):
    """Schema for batch booking expiration task."""
    
    booking_ids: List[UUID]
    batch_size: int = 100