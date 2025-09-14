"""
FastAPI routes for booking management with concurrency control.
"""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.booking_service import BookingService
from ..utils.exceptions import (
    EventlyError,
    InsufficientCapacityError,
    ConcurrencyError,
    BookingNotFoundError,
    BookingExpiredError,
    InvalidBookingStateError,
)
from ..schemas.booking import (
    BookingCreateRequest,
    BookingConfirmRequest,
    BookingCancelRequest,
    BookingResponse,
    BookingListResponse,
    CreateBookingResponse,
    ConfirmBookingResponse,
    CancelBookingResponse,
    BookingFilterRequest,
    BookingErrorResponse,
    BookingSearchRequest,
    BookingHistoryListResponse,
    BookingDashboardResponse,
    BookingDashboardStats,
    BookingReceiptResponse,
    BookingCategoryResponse,
    ReceiptLineItem,
)
from ..models.booking import BookingStatus
from ..utils.dependencies import get_current_user
from ..models.user import User
from ..config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/bookings", tags=["bookings"])
settings = get_settings()


def _create_booking_response(booking) -> BookingResponse:
    """Create a BookingResponse from a booking model."""
    seat_bookings = []
    if booking.seat_bookings:
        for sb in booking.seat_bookings:
            seat_bookings.append({
                "id": sb.id,
                "seat_id": sb.seat_id,
                "section": sb.seat.section,
                "row": sb.seat.row,
                "number": sb.seat.number,
                "price": sb.seat.price,
            })
    
    return BookingResponse(
        id=booking.id,
        user_id=booking.user_id,
        event_id=booking.event_id,
        quantity=booking.quantity,
        total_amount=booking.total_amount,
        status=booking.status,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
        expires_at=booking.expires_at,
        event_name=booking.event.name if booking.event else None,
        event_date=booking.event.event_date if booking.event else None,
        venue=booking.event.venue if booking.event else None,
        seat_bookings=seat_bookings,
    )


def _handle_booking_error(error: Exception) -> HTTPException:
    """Convert booking service errors to HTTP exceptions."""
    if isinstance(error, InsufficientCapacityError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "INSUFFICIENT_CAPACITY",
                "message": str(error),
                "suggestions": ["Try booking fewer tickets", "Join the waitlist"]
            }
        )
    elif isinstance(error, ConcurrencyError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "CONCURRENCY_CONFLICT",
                "message": str(error),
                "suggestions": ["Please try again"]
            }
        )
    elif isinstance(error, BookingNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "BOOKING_NOT_FOUND",
                "message": str(error)
            }
        )
    elif isinstance(error, BookingExpiredError):
        return HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "error_code": "BOOKING_EXPIRED",
                "message": str(error),
                "suggestions": ["Create a new booking"]
            }
        )
    elif isinstance(error, InvalidBookingStateError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_BOOKING_STATE",
                "message": str(error)
            }
        )
    elif isinstance(error, EventlyError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error.to_dict()
        )
    else:
        logger.error(f"Unexpected error in booking API: {error}")
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred"
            }
        )


@router.post("/", response_model=CreateBookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    request: BookingCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new booking for an event.
    
    This endpoint handles concurrent booking requests with optimistic locking
    to prevent overselling and ensure data consistency.
    """
    try:
        booking_service = BookingService(db)
        booking = await booking_service.create_booking(
            user_id=current_user.id,
            event_id=request.event_id,
            quantity=request.quantity,
            seat_ids=request.seat_ids
        )
        
        booking_response = _create_booking_response(booking)
        
        return CreateBookingResponse(
            booking=booking_response,
            message="Booking created successfully. Please complete payment within the time limit.",
            expires_in_minutes=settings.booking_hold_timeout_minutes
        )
        
    except Exception as e:
        raise _handle_booking_error(e)


@router.post("/{booking_id}/confirm", response_model=ConfirmBookingResponse)
async def confirm_booking(
    booking_id: UUID,
    request: BookingConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Confirm a pending booking after payment processing.
    
    This endpoint should be called after successful payment processing
    to finalize the booking and remove the expiration timeout.
    """
    try:
        booking_service = BookingService(db)
        
        # Verify booking belongs to current user
        existing_booking = await booking_service.get_booking(booking_id)
        if not existing_booking or existing_booking.user_id != current_user.id:
            raise BookingNotFoundError("Booking not found")
        
        booking = await booking_service.confirm_booking(
            booking_id=booking_id,
            payment_reference=request.payment_reference
        )
        
        booking_response = _create_booking_response(booking)
        
        return ConfirmBookingResponse(
            booking=booking_response,
            message="Booking confirmed successfully"
        )
        
    except Exception as e:
        raise _handle_booking_error(e)


@router.delete("/{booking_id}", response_model=CancelBookingResponse)
async def cancel_booking(
    booking_id: UUID,
    request: BookingCancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel a booking and release seats back to inventory.
    
    This endpoint cancels a booking and immediately makes the seats
    available for other users. Waitlisted users will be notified.
    """
    try:
        booking_service = BookingService(db)
        
        # Verify booking belongs to current user
        existing_booking = await booking_service.get_booking(booking_id)
        if not existing_booking or existing_booking.user_id != current_user.id:
            raise BookingNotFoundError("Booking not found")
        
        booking = await booking_service.cancel_booking(
            booking_id=booking_id,
            reason=request.reason
        )
        
        booking_response = _create_booking_response(booking)
        
        # Calculate potential refund amount (simplified logic)
        refund_amount = booking.total_amount if booking.status == BookingStatus.CONFIRMED else None
        
        return CancelBookingResponse(
            booking=booking_response,
            message="Booking cancelled successfully",
            refund_amount=refund_amount
        )
        
    except Exception as e:
        raise _handle_booking_error(e)


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific booking.
    
    Returns comprehensive booking information including event details
    and seat information if applicable.
    """
    try:
        booking_service = BookingService(db)
        booking = await booking_service.get_booking(booking_id)
        
        if not booking:
            raise BookingNotFoundError("Booking not found")
        
        # Verify booking belongs to current user (or user is admin)
        if booking.user_id != current_user.id and not current_user.is_admin:
            raise BookingNotFoundError("Booking not found")
        
        return _create_booking_response(booking)
        
    except Exception as e:
        raise _handle_booking_error(e)


@router.get("/", response_model=BookingListResponse)
async def get_user_bookings(
    status: List[BookingStatus] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get bookings for the current user.
    
    Returns a paginated list of bookings with optional status filtering.
    """
    try:
        booking_service = BookingService(db)
        bookings = await booking_service.get_user_bookings(
            user_id=current_user.id,
            status_filter=status,
            limit=min(limit, 100),  # Cap at 100
            offset=offset
        )
        
        booking_responses = [_create_booking_response(booking) for booking in bookings]
        
        return BookingListResponse(
            bookings=booking_responses,
            total=len(booking_responses),  # Simplified - in production, get actual count
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        raise _handle_booking_error(e)


@router.post("/search", response_model=BookingListResponse)
async def search_user_bookings(
    search_request: BookingSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Search and filter user bookings with advanced criteria.
    
    Supports searching by event name, venue, status, date range, and amount range.
    """
    try:
        booking_service = BookingService(db)
        bookings, total_count = await booking_service.search_user_bookings(
            user_id=current_user.id,
            query=search_request.query,
            status_filter=search_request.status,
            date_from=search_request.date_from,
            date_to=search_request.date_to,
            min_amount=search_request.min_amount,
            max_amount=search_request.max_amount,
            sort_by=search_request.sort_by,
            sort_order=search_request.sort_order,
            limit=search_request.limit,
            offset=search_request.offset
        )
        
        booking_responses = [_create_booking_response(booking) for booking in bookings]
        
        return BookingListResponse(
            bookings=booking_responses,
            total=total_count,
            limit=search_request.limit,
            offset=search_request.offset
        )
        
    except Exception as e:
        raise _handle_booking_error(e)


@router.get("/dashboard", response_model=BookingDashboardResponse)
async def get_user_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user booking dashboard with statistics and recent bookings.
    
    Returns booking statistics and categorized recent bookings for dashboard display.
    """
    try:
        booking_service = BookingService(db)
        
        # Get booking statistics
        stats_data = await booking_service.get_user_booking_stats(current_user.id)
        stats = BookingDashboardStats(**stats_data)
        
        # Get categorized bookings
        categorized_bookings = await booking_service.get_categorized_bookings(
            current_user.id, 
            limit_per_category=5
        )
        
        # Convert to response format
        upcoming_bookings = [_create_booking_response(booking) for booking in categorized_bookings['upcoming']]
        recent_bookings = [_create_booking_response(booking) for booking in categorized_bookings['past'][:5]]
        
        return BookingDashboardResponse(
            stats=stats,
            upcoming_bookings=upcoming_bookings,
            recent_bookings=recent_bookings
        )
        
    except Exception as e:
        raise _handle_booking_error(e)


@router.get("/categories", response_model=BookingCategoryResponse)
async def get_categorized_bookings(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user bookings categorized by status and timing.
    
    Returns bookings organized into upcoming, past, cancelled, and pending categories.
    """
    try:
        booking_service = BookingService(db)
        categorized_bookings = await booking_service.get_categorized_bookings(
            current_user.id, 
            limit_per_category=limit
        )
        
        return BookingCategoryResponse(
            upcoming=[_create_booking_response(booking) for booking in categorized_bookings['upcoming']],
            past=[_create_booking_response(booking) for booking in categorized_bookings['past']],
            cancelled=[_create_booking_response(booking) for booking in categorized_bookings['cancelled']],
            pending=[_create_booking_response(booking) for booking in categorized_bookings['pending']]
        )
        
    except Exception as e:
        raise _handle_booking_error(e)


@router.get("/{booking_id}/history", response_model=BookingHistoryListResponse)
async def get_booking_history(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the complete audit trail for a booking.
    
    Returns all historical actions performed on the booking.
    """
    try:
        booking_service = BookingService(db)
        
        # Verify booking belongs to current user (or user is admin)
        booking = await booking_service.get_booking(booking_id)
        if not booking:
            raise BookingNotFoundError("Booking not found")
        
        if booking.user_id != current_user.id and not current_user.is_admin:
            raise BookingNotFoundError("Booking not found")
        
        # Get booking history
        history = await booking_service.get_booking_history(booking_id)
        
        from ..schemas.booking import BookingHistoryResponse
        history_responses = [
            BookingHistoryResponse(
                id=entry.id,
                booking_id=entry.booking_id,
                action=entry.action,
                details=entry.details,
                performed_by=entry.performed_by,
                created_at=entry.created_at
            )
            for entry in history
        ]
        
        return BookingHistoryListResponse(
            history=history_responses,
            total=len(history_responses)
        )
        
    except Exception as e:
        raise _handle_booking_error(e)


@router.get("/{booking_id}/receipt", response_model=BookingReceiptResponse)
async def get_booking_receipt(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate and return a receipt for a booking.
    
    Returns detailed receipt information including line items and customer details.
    """
    try:
        booking_service = BookingService(db)
        
        # Verify booking belongs to current user (or user is admin)
        booking = await booking_service.get_booking(booking_id)
        if not booking:
            raise BookingNotFoundError("Booking not found")
        
        if booking.user_id != current_user.id and not current_user.is_admin:
            raise BookingNotFoundError("Booking not found")
        
        # Generate receipt
        receipt_data = await booking_service.generate_booking_receipt(booking_id)
        
        # Convert line items to proper format
        line_items = [
            ReceiptLineItem(**item) for item in receipt_data['line_items']
        ]
        
        return BookingReceiptResponse(
            booking_id=receipt_data['booking_id'],
            booking_reference=receipt_data['booking_reference'],
            event_name=receipt_data['event_name'],
            event_date=receipt_data['event_date'],
            venue=receipt_data['venue'],
            customer_name=receipt_data['customer_name'],
            customer_email=receipt_data['customer_email'],
            booking_date=receipt_data['booking_date'],
            line_items=line_items,
            subtotal=receipt_data['subtotal'],
            total_amount=receipt_data['total_amount'],
            payment_status=receipt_data['payment_status'],
            seat_details=receipt_data['seat_details']
        )
        
    except Exception as e:
        raise _handle_booking_error(e)


# Admin endpoints

@router.get("/admin/expired", response_model=List[BookingResponse])
async def get_expired_bookings(
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get expired bookings that need processing (Admin only).
    
    This endpoint is used by background tasks to identify and process
    expired bookings that need to be cleaned up.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        booking_service = BookingService(db)
        expired_bookings = await booking_service.get_expired_bookings(limit=limit)
        
        return [_create_booking_response(booking) for booking in expired_bookings]
        
    except Exception as e:
        raise _handle_booking_error(e)


@router.post("/admin/{booking_id}/expire", response_model=BookingResponse)
async def expire_booking(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually expire a booking (Admin only).
    
    This endpoint allows administrators to manually expire bookings
    and is also used by background tasks for automated expiration.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        booking_service = BookingService(db)
        booking = await booking_service.expire_booking(booking_id)
        
        return _create_booking_response(booking)
        
    except Exception as e:
        raise _handle_booking_error(e)