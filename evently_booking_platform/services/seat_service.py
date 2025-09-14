"""
Seat service for managing venue seating and seat operations.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import and_, select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from evently_booking_platform.models import Seat, SeatStatus, Event, SeatBooking, Booking, BookingStatus
from evently_booking_platform.schemas.seat import (
    SeatCreate, SeatUpdate, SeatMapResponse, SeatAvailabilityResponse,
    SeatHoldRequest, SeatHoldResponse
)
from evently_booking_platform.utils.exceptions import (
    SeatNotFoundError, SeatNotAvailableError, EventNotFoundError,
    ValidationError, SeatHoldExpiredError
)
from evently_booking_platform.cache import (
    get_cache, CacheKeyBuilder, CacheTTL, CacheInvalidator, distributed_lock
)

logger = logging.getLogger(__name__)


class SeatService:
    """Service class for seat management operations."""
    
    # Default seat hold duration in minutes
    SEAT_HOLD_DURATION = 15
    
    def __init__(self, db: AsyncSession):
        """Initialize the seat service with database session."""
        self.db = db
        self.cache = get_cache()
    
    async def create_seats_for_event(
        self, 
        event_id: UUID, 
        seats_data: List[SeatCreate]
    ) -> List[Seat]:
        """
        Create multiple seats for an event.
        
        Args:
            event_id: Event UUID
            seats_data: List of seat creation data
            
        Returns:
            List of created seat instances
            
        Raises:
            EventNotFoundError: If event is not found
            ValidationError: If seat data is invalid
        """
        # Verify event exists
        event_result = await self.db.execute(
            select(Event).where(Event.id == event_id)
        )
        event = event_result.scalar_one_or_none()
        if not event:
            raise EventNotFoundError(f"Event with ID {event_id} not found")
        
        try:
            seats = []
            for seat_data in seats_data:
                seat = Seat(
                    event_id=event_id,
                    section=seat_data.section,
                    row=seat_data.row,
                    number=seat_data.number,
                    price=seat_data.price,
                    status=SeatStatus.AVAILABLE
                )
                seats.append(seat)
                self.db.add(seat)
            
            await self.db.commit()
            
            # Refresh all seats to get their IDs
            for seat in seats:
                await self.db.refresh(seat)
            
            # Invalidate seat caches for this event
            await CacheInvalidator.invalidate_seat_caches(str(event_id))
            
            return seats
            
        except IntegrityError as e:
            await self.db.rollback()
            raise ValidationError(f"Failed to create seats: {str(e)}")
    
    async def get_seat_map(self, event_id: UUID) -> SeatMapResponse:
        """
        Get the seat map for an event with caching.
        
        Args:
            event_id: Event UUID
            
        Returns:
            Seat map response with organized seat data
            
        Raises:
            EventNotFoundError: If event is not found
        """
        # Try to get from cache first
        cache_key = CacheKeyBuilder.seat_map(str(event_id))
        cached_seat_map = await self.cache.get(cache_key)
        
        if cached_seat_map:
            return SeatMapResponse(**cached_seat_map)
        # Verify event exists
        event_result = await self.db.execute(
            select(Event).where(Event.id == event_id)
        )
        event = event_result.scalar_one_or_none()
        if not event:
            raise EventNotFoundError(f"Event with ID {event_id} not found")
        
        # Get all seats for the event
        seats_result = await self.db.execute(
            select(Seat)
            .where(Seat.event_id == event_id)
            .order_by(Seat.section, Seat.row, Seat.number)
        )
        seats = seats_result.scalars().all()
        
        # Organize seats by section and row
        seat_map = {}
        for seat in seats:
            if seat.section not in seat_map:
                seat_map[seat.section] = {}
            if seat.row not in seat_map[seat.section]:
                seat_map[seat.section][seat.row] = []
            
            seat_map[seat.section][seat.row].append({
                "id": str(seat.id),
                "number": seat.number,
                "price": float(seat.price),
                "status": seat.status.value,
                "is_available": seat.is_available
            })
        
        # Calculate availability statistics
        total_seats = len(seats)
        available_seats = sum(1 for seat in seats if seat.is_available)
        held_seats = sum(1 for seat in seats if seat.status == SeatStatus.HELD)
        booked_seats = sum(1 for seat in seats if seat.status == SeatStatus.BOOKED)
        
        seat_map_response = SeatMapResponse(
            event_id=str(event_id),
            seat_map=seat_map,
            total_seats=total_seats,
            available_seats=available_seats,
            held_seats=held_seats,
            booked_seats=booked_seats
        )
        
        # Cache the seat map
        await self.cache.set(
            cache_key, 
            seat_map_response.model_dump(), 
            CacheTTL.SEAT_MAP
        )
        
        return seat_map_response
    
    async def check_seat_availability(
        self, 
        seat_ids: List[UUID]
    ) -> SeatAvailabilityResponse:
        """
        Check availability of specific seats.
        
        Args:
            seat_ids: List of seat UUIDs to check
            
        Returns:
            Seat availability response
        """
        # Get seats
        seats_result = await self.db.execute(
            select(Seat).where(Seat.id.in_(seat_ids))
        )
        seats = seats_result.scalars().all()
        
        # Check availability
        available_seats = []
        unavailable_seats = []
        
        for seat in seats:
            seat_info = {
                "id": str(seat.id),
                "section": seat.section,
                "row": seat.row,
                "number": seat.number,
                "price": float(seat.price),
                "status": seat.status.value
            }
            
            if seat.is_available:
                available_seats.append(seat_info)
            else:
                unavailable_seats.append(seat_info)
        
        # Check for missing seats
        found_seat_ids = {seat.id for seat in seats}
        missing_seat_ids = [
            str(seat_id) for seat_id in seat_ids 
            if seat_id not in found_seat_ids
        ]
        
        return SeatAvailabilityResponse(
            available_seats=available_seats,
            unavailable_seats=unavailable_seats,
            missing_seat_ids=missing_seat_ids,
            all_available=len(unavailable_seats) == 0 and len(missing_seat_ids) == 0
        )
    
    async def hold_seats(
        self, 
        seat_ids: List[UUID], 
        hold_duration_minutes: Optional[int] = None
    ) -> SeatHoldResponse:
        """
        Temporarily hold seats for booking with distributed locking.
        
        Args:
            seat_ids: List of seat UUIDs to hold
            hold_duration_minutes: Hold duration in minutes (default: 15)
            
        Returns:
            Seat hold response
            
        Raises:
            SeatNotAvailableError: If any seat is not available
        """
        hold_duration = hold_duration_minutes or self.SEAT_HOLD_DURATION
        expires_at = datetime.utcnow() + timedelta(minutes=hold_duration)
        
        try:
            # Check availability first
            availability = await self.check_seat_availability(seat_ids)
            if not availability.all_available:
                unavailable_info = []
                if availability.unavailable_seats:
                    unavailable_info.extend([
                        f"{seat['section']}-{seat['row']}-{seat['number']} ({seat['status']})"
                        for seat in availability.unavailable_seats
                    ])
                if availability.missing_seat_ids:
                    unavailable_info.extend([
                        f"Seat ID {seat_id} (not found)"
                        for seat_id in availability.missing_seat_ids
                    ])
                
                raise SeatNotAvailableError(
                    f"Cannot hold seats. Unavailable: {', '.join(unavailable_info)}"
                )
            
            # Hold the seats
            await self.db.execute(
                update(Seat)
                .where(
                    and_(
                        Seat.id.in_(seat_ids),
                        Seat.status == SeatStatus.AVAILABLE
                    )
                )
                .values(status=SeatStatus.HELD)
            )
            
            await self.db.commit()
            
            # Invalidate seat caches after holding seats
            if seat_ids:
                # Get event_id from first seat to invalidate caches
                first_seat_result = await self.db.execute(
                    select(Seat.event_id).where(Seat.id == seat_ids[0])
                )
                event_id = first_seat_result.scalar_one_or_none()
                if event_id:
                    await CacheInvalidator.invalidate_seat_caches(str(event_id))
            
            return SeatHoldResponse(
                held_seat_ids=[str(seat_id) for seat_id in seat_ids],
                expires_at=expires_at,
                hold_duration_minutes=hold_duration
            )
            
        except IntegrityError as e:
            await self.db.rollback()
            raise ValidationError(f"Failed to hold seats: {str(e)}")
    
    async def release_held_seats(self, seat_ids: List[UUID]) -> None:
        """
        Release held seats back to available status.
        
        Args:
            seat_ids: List of seat UUIDs to release
        """
        try:
            await self.db.execute(
                update(Seat)
                .where(
                    and_(
                        Seat.id.in_(seat_ids),
                        Seat.status == SeatStatus.HELD
                    )
                )
                .values(status=SeatStatus.AVAILABLE)
            )
            
            await self.db.commit()
            
            # Invalidate seat caches after releasing seats
            if seat_ids:
                # Get event_id from first seat to invalidate caches
                first_seat_result = await self.db.execute(
                    select(Seat.event_id).where(Seat.id == seat_ids[0])
                )
                event_id = first_seat_result.scalar_one_or_none()
                if event_id:
                    await CacheInvalidator.invalidate_seat_caches(str(event_id))
            
        except IntegrityError as e:
            await self.db.rollback()
            raise ValidationError(f"Failed to release held seats: {str(e)}")
    
    async def book_seats(
        self, 
        seat_ids: List[UUID], 
        booking_id: UUID
    ) -> List[Seat]:
        """
        Book seats and create seat booking records.
        
        Args:
            seat_ids: List of seat UUIDs to book
            booking_id: Booking UUID
            
        Returns:
            List of booked seat instances
            
        Raises:
            SeatNotAvailableError: If any seat is not available for booking
        """
        try:
            # Get seats and verify they can be booked (available or held)
            seats_result = await self.db.execute(
                select(Seat).where(Seat.id.in_(seat_ids))
            )
            seats = seats_result.scalars().all()
            
            # Check if all seats can be booked
            bookable_statuses = {SeatStatus.AVAILABLE, SeatStatus.HELD}
            unbookable_seats = [
                seat for seat in seats 
                if seat.status not in bookable_statuses
            ]
            
            if unbookable_seats:
                unbookable_info = [
                    f"{seat.section}-{seat.row}-{seat.number} ({seat.status.value})"
                    for seat in unbookable_seats
                ]
                raise SeatNotAvailableError(
                    f"Cannot book seats. Unavailable: {', '.join(unbookable_info)}"
                )
            
            # Update seat status to booked
            await self.db.execute(
                update(Seat)
                .where(Seat.id.in_(seat_ids))
                .values(status=SeatStatus.BOOKED)
            )
            
            # Create seat booking records
            for seat in seats:
                seat_booking = SeatBooking(
                    booking_id=booking_id,
                    seat_id=seat.id
                )
                self.db.add(seat_booking)
            
            await self.db.commit()
            
            # Refresh seats to get updated status
            for seat in seats:
                await self.db.refresh(seat)
            
            # Invalidate seat caches after booking seats
            if seats:
                await CacheInvalidator.invalidate_seat_caches(str(seats[0].event_id))
            
            return seats
            
        except IntegrityError as e:
            await self.db.rollback()
            raise ValidationError(f"Failed to book seats: {str(e)}")
    
    async def release_booked_seats(self, booking_id: UUID) -> None:
        """
        Release booked seats when a booking is cancelled.
        
        Args:
            booking_id: Booking UUID
        """
        try:
            # Get seat IDs from seat bookings
            seat_bookings_result = await self.db.execute(
                select(SeatBooking.seat_id)
                .where(SeatBooking.booking_id == booking_id)
            )
            seat_ids = [row[0] for row in seat_bookings_result.fetchall()]
            
            if seat_ids:
                # Update seat status back to available
                await self.db.execute(
                    update(Seat)
                    .where(Seat.id.in_(seat_ids))
                    .values(status=SeatStatus.AVAILABLE)
                )
                
                # Delete seat booking records
                await self.db.execute(
                    select(SeatBooking)
                    .where(SeatBooking.booking_id == booking_id)
                )
                
                # Invalidate seat caches after releasing booked seats
                # Get event_id from first seat to invalidate caches
                first_seat_result = await self.db.execute(
                    select(Seat.event_id).where(Seat.id == seat_ids[0])
                )
                event_id = first_seat_result.scalar_one_or_none()
                if event_id:
                    await CacheInvalidator.invalidate_seat_caches(str(event_id))
            
            await self.db.commit()
            
        except IntegrityError as e:
            await self.db.rollback()
            raise ValidationError(f"Failed to release booked seats: {str(e)}")
    
    async def cleanup_expired_holds(self) -> int:
        """
        Clean up expired seat holds.
        
        Returns:
            Number of seats released from expired holds
        """
        try:
            # This is a simplified cleanup - in a real system, you'd track hold expiration times
            # For now, we'll assume held seats older than SEAT_HOLD_DURATION are expired
            cutoff_time = datetime.utcnow() - timedelta(minutes=self.SEAT_HOLD_DURATION)
            
            # Get held seats that might be expired
            # Note: This is a simplified approach. In production, you'd store hold timestamps
            held_seats_result = await self.db.execute(
                select(Seat)
                .where(
                    and_(
                        Seat.status == SeatStatus.HELD,
                        Seat.updated_at < cutoff_time
                    )
                )
            )
            held_seats = held_seats_result.scalars().all()
            
            if held_seats:
                seat_ids = [seat.id for seat in held_seats]
                await self.db.execute(
                    update(Seat)
                    .where(Seat.id.in_(seat_ids))
                    .values(status=SeatStatus.AVAILABLE)
                )
                
                await self.db.commit()
                return len(held_seats)
            
            return 0
            
        except IntegrityError as e:
            await self.db.rollback()
            raise ValidationError(f"Failed to cleanup expired holds: {str(e)}")
    
    async def get_seat_pricing_tiers(self, event_id: UUID) -> Dict[str, Any]:
        """
        Get seat pricing information organized by tiers.
        
        Args:
            event_id: Event UUID
            
        Returns:
            Dictionary with pricing tier information
        """
        # Get all seats for the event with pricing info
        seats_result = await self.db.execute(
            select(Seat.section, Seat.price, func.count(Seat.id).label('count'))
            .where(Seat.event_id == event_id)
            .group_by(Seat.section, Seat.price)
            .order_by(Seat.price.desc())
        )
        
        pricing_data = seats_result.fetchall()
        
        # Organize by price tiers
        tiers = {}
        for section, price, count in pricing_data:
            price_key = f"${float(price):.2f}"
            if price_key not in tiers:
                tiers[price_key] = {
                    "price": float(price),
                    "sections": [],
                    "total_seats": 0
                }
            
            tiers[price_key]["sections"].append({
                "section": section,
                "seat_count": count
            })
            tiers[price_key]["total_seats"] += count
        
        return {
            "event_id": str(event_id),
            "pricing_tiers": tiers
        }
    
    async def update_seat_pricing(
        self, 
        event_id: UUID, 
        section: str, 
        new_price: float
    ) -> int:
        """
        Update pricing for all seats in a specific section.
        
        Args:
            event_id: Event UUID
            section: Section name
            new_price: New price for the section
            
        Returns:
            Number of seats updated
        """
        try:
            result = await self.db.execute(
                update(Seat)
                .where(
                    and_(
                        Seat.event_id == event_id,
                        Seat.section == section
                    )
                )
                .values(price=new_price)
            )
            
            await self.db.commit()
            return result.rowcount
            
        except IntegrityError as e:
            await self.db.rollback()
            raise ValidationError(f"Failed to update seat pricing: {str(e)}")