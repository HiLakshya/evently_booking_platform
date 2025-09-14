"""
Bulk booking service for group purchases and large quantity bookings.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
import secrets
import string

from sqlalchemy import select, and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from evently_booking_platform.models import (
    Event, Booking, BookingStatus, Seat, SeatStatus, SeatBooking, User
)
from evently_booking_platform.schemas.advanced_analytics import (
    BulkBookingRequest, BulkBookingResponse
)
from evently_booking_platform.utils.exceptions import (
    EventNotFoundError, InsufficientCapacityError, ValidationError
)
from evently_booking_platform.services.booking_service import BookingService
from evently_booking_platform.cache import get_cache, distributed_lock

logger = logging.getLogger(__name__)


class BulkBookingService:
    """Service for handling bulk booking operations."""

    def __init__(self, db: AsyncSession):
        """Initialize the bulk booking service."""
        self.db = db
        self.cache = get_cache()
        self.booking_service = BookingService(db)

    async def create_bulk_booking(
        self,
        request: BulkBookingRequest
    ) -> BulkBookingResponse:
        """Create a bulk booking for multiple seats/tickets."""
        # Validate request
        if request.quantity < 2:
            raise ValidationError("Bulk bookings require at least 2 tickets")
        
        if request.quantity > 100:
            raise ValidationError("Bulk bookings are limited to 100 tickets maximum")

        # Get event details
        event_query = select(Event).where(Event.id == request.event_id)
        event_result = await self.db.execute(event_query)
        event = event_result.scalar_one_or_none()
        
        if not event:
            raise EventNotFoundError(f"Event {request.event_id} not found")

        # Check availability
        if event.available_capacity < request.quantity:
            raise InsufficientCapacityError(
                f"Insufficient capacity. Requested: {request.quantity}, Available: {event.available_capacity}"
            )

        # Use distributed lock for bulk booking
        lock_key = f"bulk_booking:{request.event_id}"
        async with distributed_lock(lock_key, timeout=30):
            return await self._process_bulk_booking(event, request)

    async def _process_bulk_booking(
        self,
        event: Event,
        request: BulkBookingRequest
    ) -> BulkBookingResponse:
        """Process the bulk booking with seat assignment."""
        # Calculate pricing with bulk discounts
        base_price = event.price
        total_base_amount = base_price * request.quantity
        
        # Apply group discount based on quantity
        group_discount_percentage = self._calculate_group_discount(request.quantity)
        discount_amount = total_base_amount * (group_discount_percentage / 100)
        
        # Apply discount code if provided
        discount_code_amount = Decimal('0.00')
        if request.discount_code:
            discount_code_amount = await self._apply_discount_code(
                request.discount_code, total_base_amount
            )
        
        total_discount = discount_amount + discount_code_amount
        final_amount = total_base_amount - total_discount

        # Create the main booking record
        booking = Booking(
            id=uuid4(),
            user_id=request.user_id,
            event_id=request.event_id,
            quantity=request.quantity,
            total_amount=final_amount,
            status=BookingStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(minutes=15),  # 15 min to complete
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(booking)

        # Handle seat assignments
        seat_assignments = []
        if event.has_seat_selection:
            if request.seat_ids:
                # Use specific seats requested
                seat_assignments = await self._assign_specific_seats(
                    booking.id, request.seat_ids
                )
            else:
                # Auto-assign best available seats
                seat_assignments = await self._auto_assign_seats(
                    booking.id, event.id, request.quantity
                )
        else:
            # General admission - no specific seats
            seat_assignments = [
                {
                    "type": "general_admission",
                    "quantity": request.quantity,
                    "section": "General Admission"
                }
            ]

        # Update event capacity
        await self.db.execute(
            update(Event)
            .where(Event.id == request.event_id)
            .values(
                available_capacity=Event.available_capacity - request.quantity,
                updated_at=datetime.utcnow()
            )
        )

        # Generate confirmation code
        confirmation_code = self._generate_confirmation_code()

        # Commit the transaction
        await self.db.commit()

        return BulkBookingResponse(
            booking_id=booking.id,
            event_id=request.event_id,
            total_quantity=request.quantity,
            total_amount=final_amount,
            discount_applied=total_discount if total_discount > 0 else None,
            group_discount_percentage=group_discount_percentage if group_discount_percentage > 0 else None,
            seat_assignments=seat_assignments,
            confirmation_code=confirmation_code
        )

    def _calculate_group_discount(self, quantity: int) -> float:
        """Calculate group discount percentage based on quantity."""
        if quantity >= 50:
            return 15.0  # 15% discount for 50+ tickets
        elif quantity >= 20:
            return 10.0  # 10% discount for 20+ tickets
        elif quantity >= 10:
            return 5.0   # 5% discount for 10+ tickets
        else:
            return 0.0   # No discount for less than 10 tickets

    async def _apply_discount_code(
        self,
        discount_code: str,
        base_amount: Decimal
    ) -> Decimal:
        """Apply discount code if valid."""
        # Simplified discount code logic
        # In a real system, this would check a discount_codes table
        discount_codes = {
            "BULK10": 0.10,  # 10% discount
            "BULK15": 0.15,  # 15% discount
            "EARLYBIRD": 0.20,  # 20% discount
            "STUDENT": 0.25   # 25% discount
        }
        
        discount_percentage = discount_codes.get(discount_code.upper(), 0.0)
        return base_amount * Decimal(str(discount_percentage))

    async def _assign_specific_seats(
        self,
        booking_id: UUID,
        seat_ids: List[UUID]
    ) -> List[Dict[str, Any]]:
        """Assign specific seats to the booking."""
        # Get seat details
        seats_query = select(Seat).where(
            and_(
                Seat.id.in_(seat_ids),
                Seat.status == SeatStatus.AVAILABLE
            )
        )
        seats_result = await self.db.execute(seats_query)
        seats = seats_result.scalars().all()

        if len(seats) != len(seat_ids):
            raise ValidationError("Some requested seats are not available")

        seat_assignments = []
        
        # Create seat bookings and update seat status
        for seat in seats:
            seat_booking = SeatBooking(
                id=uuid4(),
                booking_id=booking_id,
                seat_id=seat.id,
                created_at=datetime.utcnow()
            )
            self.db.add(seat_booking)

            # Update seat status
            await self.db.execute(
                update(Seat)
                .where(Seat.id == seat.id)
                .values(
                    status=SeatStatus.BOOKED,
                    updated_at=datetime.utcnow()
                )
            )

            seat_assignments.append({
                "seat_id": str(seat.id),
                "section": seat.section,
                "row": seat.row,
                "number": seat.number,
                "price": float(seat.price)
            })

        return seat_assignments

    async def _auto_assign_seats(
        self,
        booking_id: UUID,
        event_id: UUID,
        quantity: int
    ) -> List[Dict[str, Any]]:
        """Auto-assign best available seats for the booking."""
        # Get available seats, preferring contiguous seating
        seats_query = select(Seat).where(
            and_(
                Seat.event_id == event_id,
                Seat.status == SeatStatus.AVAILABLE
            )
        ).order_by(
            Seat.section,
            Seat.row,
            Seat.number
        ).limit(quantity * 2)  # Get more seats to find best contiguous group

        seats_result = await self.db.execute(seats_query)
        available_seats = seats_result.scalars().all()

        if len(available_seats) < quantity:
            raise InsufficientCapacityError("Not enough seats available")

        # Find best contiguous group
        selected_seats = self._find_best_seat_group(available_seats, quantity)

        seat_assignments = []
        
        # Create seat bookings
        for seat in selected_seats:
            seat_booking = SeatBooking(
                id=uuid4(),
                booking_id=booking_id,
                seat_id=seat.id,
                created_at=datetime.utcnow()
            )
            self.db.add(seat_booking)

            # Update seat status
            await self.db.execute(
                update(Seat)
                .where(Seat.id == seat.id)
                .values(
                    status=SeatStatus.BOOKED,
                    updated_at=datetime.utcnow()
                )
            )

            seat_assignments.append({
                "seat_id": str(seat.id),
                "section": seat.section,
                "row": seat.row,
                "number": seat.number,
                "price": float(seat.price)
            })

        return seat_assignments

    def _find_best_seat_group(self, available_seats: List[Seat], quantity: int) -> List[Seat]:
        """Find the best group of seats for bulk booking."""
        # Group seats by section and row
        seat_groups = {}
        for seat in available_seats:
            key = f"{seat.section}_{seat.row}"
            if key not in seat_groups:
                seat_groups[key] = []
            seat_groups[key].append(seat)

        # Find the best contiguous group
        best_group = []
        
        for group_key, seats in seat_groups.items():
            if len(seats) >= quantity:
                # Sort by seat number
                seats.sort(key=lambda s: int(s.number) if s.number.isdigit() else 999)
                
                # Try to find contiguous seats
                contiguous_group = self._find_contiguous_group(seats, quantity)
                if len(contiguous_group) == quantity:
                    best_group = contiguous_group
                    break

        # If no contiguous group found, take best available seats
        if not best_group:
            best_group = available_seats[:quantity]

        return best_group

    def _find_contiguous_group(self, seats: List[Seat], quantity: int) -> List[Seat]:
        """Find a contiguous group of seats."""
        for i in range(len(seats) - quantity + 1):
            group = [seats[i]]
            current_num = int(seats[i].number) if seats[i].number.isdigit() else None
            
            if current_num is None:
                continue
                
            for j in range(i + 1, min(i + quantity, len(seats))):
                next_seat = seats[j]
                next_num = int(next_seat.number) if next_seat.number.isdigit() else None
                
                if next_num is None or next_num != current_num + 1:
                    break
                    
                group.append(next_seat)
                current_num = next_num
            
            if len(group) == quantity:
                return group
        
        return []

    def _generate_confirmation_code(self) -> str:
        """Generate a unique confirmation code."""
        return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))