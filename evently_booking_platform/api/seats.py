"""
Seat management API endpoints.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from evently_booking_platform.database import get_db
from evently_booking_platform.utils.dependencies import get_current_user, require_admin
from evently_booking_platform.models import User
from evently_booking_platform.services.seat_service import SeatService
from evently_booking_platform.schemas.seat import (
    SeatResponse, SeatMapResponse, SeatAvailabilityResponse,
    SeatHoldRequest, SeatHoldResponse, SeatBookingRequest,
    SeatPricingTierResponse, SeatPricingUpdateRequest,
    BulkSeatCreateRequest, SeatStatistics
)
from evently_booking_platform.utils.exceptions import (
    SeatNotFoundError, SeatNotAvailableError, EventNotFoundError,
    ValidationError, SeatHoldExpiredError
)

router = APIRouter(prefix="/seats", tags=["seats"])


@router.get("/{event_id}/map", response_model=SeatMapResponse)
async def get_seat_map(
    event_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get the seat map for an event.
    
    Args:
        event_id: Event UUID
        db: Database session
        
    Returns:
        Seat map with availability information
    """
    try:
        seat_service = SeatService(db)
        seat_map = await seat_service.get_seat_map(event_id)
        return seat_map
    except EventNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get seat map: {str(e)}"
        )


@router.post("/check-availability", response_model=SeatAvailabilityResponse)
async def check_seat_availability(
    seat_ids: List[UUID],
    db: AsyncSession = Depends(get_db)
):
    """
    Check availability of specific seats.
    
    Args:
        seat_ids: List of seat UUIDs to check
        db: Database session
        
    Returns:
        Seat availability information
    """
    try:
        seat_service = SeatService(db)
        availability = await seat_service.check_seat_availability(seat_ids)
        return availability
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check seat availability: {str(e)}"
        )


@router.post("/hold", response_model=SeatHoldResponse)
async def hold_seats(
    hold_request: SeatHoldRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Hold seats temporarily for booking.
    
    Args:
        hold_request: Seat hold request data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Seat hold confirmation with expiration time
    """
    try:
        seat_service = SeatService(db)
        hold_response = await seat_service.hold_seats(
            seat_ids=hold_request.seat_ids,
            hold_duration_minutes=hold_request.hold_duration_minutes
        )
        return hold_response
    except SeatNotAvailableError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to hold seats: {str(e)}"
        )


@router.post("/release-hold")
async def release_held_seats(
    seat_ids: List[UUID],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Release held seats back to available status.
    
    Args:
        seat_ids: List of seat UUIDs to release
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Success confirmation
    """
    try:
        seat_service = SeatService(db)
        await seat_service.release_held_seats(seat_ids)
        return {"message": f"Released {len(seat_ids)} held seats"}
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to release held seats: {str(e)}"
        )


@router.get("/{event_id}/pricing", response_model=SeatPricingTierResponse)
async def get_seat_pricing_tiers(
    event_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get seat pricing information organized by tiers.
    
    Args:
        event_id: Event UUID
        db: Database session
        
    Returns:
        Pricing tier information
    """
    try:
        seat_service = SeatService(db)
        pricing_tiers = await seat_service.get_seat_pricing_tiers(event_id)
        return pricing_tiers
    except EventNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get pricing tiers: {str(e)}"
        )


# Admin-only endpoints

@router.post("/{event_id}/bulk-create", response_model=List[SeatResponse])
async def create_seats_bulk(
    event_id: UUID,
    bulk_request: BulkSeatCreateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create multiple seats for an event (Admin only).
    
    Args:
        event_id: Event UUID
        bulk_request: Bulk seat creation request
        current_user: Current authenticated admin user
        db: Database session
        
    Returns:
        List of created seats
    """
    try:
        seat_service = SeatService(db)
        seats = await seat_service.create_seats_for_event(
            event_id=event_id,
            seats_data=bulk_request.seats
        )
        return [SeatResponse.model_validate(seat) for seat in seats]
    except EventNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create seats: {str(e)}"
        )


@router.put("/{event_id}/pricing", response_model=dict)
async def update_seat_pricing(
    event_id: UUID,
    pricing_update: SeatPricingUpdateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update pricing for all seats in a specific section (Admin only).
    
    Args:
        event_id: Event UUID
        pricing_update: Pricing update request
        current_user: Current authenticated admin user
        db: Database session
        
    Returns:
        Update confirmation with count of affected seats
    """
    try:
        seat_service = SeatService(db)
        updated_count = await seat_service.update_seat_pricing(
            event_id=event_id,
            section=pricing_update.section,
            new_price=pricing_update.new_price
        )
        return {
            "message": f"Updated pricing for {updated_count} seats in section {pricing_update.section}",
            "updated_count": updated_count,
            "new_price": float(pricing_update.new_price)
        }
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update seat pricing: {str(e)}"
        )


@router.post("/cleanup-expired-holds", response_model=dict)
async def cleanup_expired_holds(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Clean up expired seat holds (Admin only).
    
    Args:
        current_user: Current authenticated admin user
        db: Database session
        
    Returns:
        Cleanup results
    """
    try:
        seat_service = SeatService(db)
        released_count = await seat_service.cleanup_expired_holds()
        return {
            "message": f"Released {released_count} expired seat holds",
            "released_count": released_count
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup expired holds: {str(e)}"
        )


@router.get("/{event_id}/statistics", response_model=SeatStatistics)
async def get_seat_statistics(
    event_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed seat statistics for an event (Admin only).
    
    Args:
        event_id: Event UUID
        current_user: Current authenticated admin user
        db: Database session
        
    Returns:
        Detailed seat statistics
    """
    try:
        seat_service = SeatService(db)
        seat_map = await seat_service.get_seat_map(event_id)
        pricing_tiers = await seat_service.get_seat_pricing_tiers(event_id)
        
        # Calculate revenue metrics
        total_revenue_potential = sum(
            tier_data["price"] * tier_data["total_seats"]
            for tier_data in pricing_tiers["pricing_tiers"].values()
        )
        
        # Estimate current revenue (booked seats)
        current_revenue = total_revenue_potential * (
            seat_map.booked_seats / seat_map.total_seats if seat_map.total_seats > 0 else 0
        )
        
        capacity_utilization = (
            (seat_map.total_seats - seat_map.available_seats) / seat_map.total_seats * 100
            if seat_map.total_seats > 0 else 0
        )
        
        return SeatStatistics(
            event_id=str(event_id),
            total_seats=seat_map.total_seats,
            available_seats=seat_map.available_seats,
            held_seats=seat_map.held_seats,
            booked_seats=seat_map.booked_seats,
            blocked_seats=0,  # Not implemented yet
            capacity_utilization=capacity_utilization,
            revenue_potential=total_revenue_potential,
            current_revenue=current_revenue
        )
    except EventNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get seat statistics: {str(e)}"
        )