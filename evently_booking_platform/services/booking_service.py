"""
Booking service with concurrency control for managing ticket reservations.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID, uuid4

from sqlalchemy import select, update, and_, or_, func, desc, asc, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.booking import Booking, BookingStatus
from ..models.event import Event
from ..models.seat import Seat, SeatStatus
from ..models.seat_booking import SeatBooking
from ..models.booking_history import BookingHistory, BookingAction
from ..models.user import User
from ..models.waitlist import Waitlist
from ..config import get_settings
from ..cache import get_cache, CacheKeyBuilder, distributed_lock, CacheInvalidator
from ..utils.exceptions import (
    InsufficientCapacityError,
    ConcurrencyError,
    BookingNotFoundError,
    BookingExpiredError,
    InvalidBookingStateError,
    OptimisticLockError,
    EventNotFoundError
)
from ..utils.retry import retry_on_concurrency_error
from ..utils.circuit_breaker import get_circuit_breaker, CircuitBreakerConfig

logger = logging.getLogger(__name__)


class BookingService:
    """Service for managing bookings with concurrency control."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.cache = get_cache()
    
    @retry_on_concurrency_error(max_attempts=3, base_delay=0.1, max_delay=1.0)
    async def create_booking(
        self,
        user_id: UUID,
        event_id: UUID,
        quantity: int,
        seat_ids: Optional[List[UUID]] = None
    ) -> Booking:
        """
        Create a new booking with optimistic locking and capacity validation.
        
        Args:
            user_id: ID of the user making the booking
            event_id: ID of the event to book
            quantity: Number of tickets to book
            seat_ids: Optional list of specific seat IDs for seat selection
            
        Returns:
            Created booking instance
            
        Raises:
            InsufficientCapacityError: When there's not enough capacity
            ConcurrencyError: When a concurrency conflict occurs
            BookingError: For other booking-related errors
        """
        logger.info(f"Creating booking for user {user_id}, event {event_id}, quantity {quantity}")
        
        # Use distributed lock for booking process
        lock_key = CacheKeyBuilder.booking_lock(str(event_id), str(user_id))
        
        async with distributed_lock(lock_key, timeout=30):
            try:
                # Start transaction
                async with self.session.begin():
                    # Get event with optimistic locking
                    event = await self._get_event_with_lock(event_id)
                    
                    # Validate booking request
                    await self._validate_booking_request(event, quantity, seat_ids)
                    
                    # Calculate total amount
                    total_amount = await self._calculate_total_amount(event, quantity, seat_ids)
                    
                    # Create booking with expiration
                    expires_at = datetime.utcnow() + timedelta(
                        minutes=self.settings.booking_hold_timeout_minutes
                    )
                    
                    booking = Booking(
                        user_id=user_id,
                        event_id=event_id,
                        quantity=quantity,
                        total_amount=total_amount,
                        status=BookingStatus.PENDING,
                        expires_at=expires_at
                    )
                    
                    # Set ID if not already set (for testing purposes)
                    if not booking.id:
                        booking.id = uuid4()
                    
                    self.session.add(booking)
                    await self.session.flush()  # Get booking ID
                    
                    # Handle seat selection if specified
                    if seat_ids:
                        await self._reserve_specific_seats(booking, seat_ids)
                    else:
                        # Update event capacity with optimistic locking
                        await self._update_event_capacity(event, quantity)
                    
                    # Create booking history entry
                    if booking.id:  # Only create history if booking has ID
                        await self._create_booking_history(
                            booking.id,
                            "CREATED",
                            f"Booking created for {quantity} tickets"
                        )
                    
                    # Ensure booking is properly committed
                    await self.session.commit()
                    
                    logger.info(f"Booking {booking.id} created successfully")
                    return booking
                
            except Exception as e:
                # Check if it's a concurrency-related error
                if "version" in str(e).lower() or "concurrent" in str(e).lower():
                    await self.session.rollback()
                    raise ConcurrencyError("Event was modified by another transaction. Please try again.")
                elif isinstance(e, IntegrityError):
                    await self.session.rollback()
                    logger.error(f"Database integrity error during booking creation: {e}")
                    raise BookingError("Failed to create booking due to data conflict")
                else:
                    await self.session.rollback()
                    logger.error(f"Unexpected error during booking creation: {e}")
                    raise BookingError(f"Failed to create booking: {str(e)}")
    
    async def confirm_booking(self, booking_id: UUID, payment_reference: Optional[str] = None) -> Booking:
        """
        Confirm a pending booking after payment processing.
        
        Args:
            booking_id: ID of the booking to confirm
            payment_reference: Optional payment reference
            
        Returns:
            Confirmed booking instance
            
        Raises:
            BookingNotFoundError: When booking is not found
            InvalidBookingStateError: When booking is not in pending state
            BookingExpiredError: When booking has expired
        """
        logger.info(f"Confirming booking {booking_id}")
        
        try:
            async with self.session.begin():
                # Get booking with related data
                booking = await self._get_booking_with_relations(booking_id)
                
                # Validate booking can be confirmed
                self._validate_booking_confirmation(booking)
                
                # Update booking status
                booking.status = BookingStatus.CONFIRMED
                booking.expires_at = None  # Remove expiration
                
                # Create booking history entry
                history_details = f"Booking confirmed"
                if payment_reference:
                    history_details += f" with payment reference: {payment_reference}"
                
                await self._create_booking_history(
                    booking.id,
                    "CONFIRMED",
                    history_details
                )
                
                await self.session.commit()
                
                # Trigger booking confirmation notification
                try:
                    from ..tasks.notification_tasks import send_booking_confirmation_task
                    send_booking_confirmation_task.delay(str(booking_id))
                    logger.info(f"Booking confirmation notification queued for {booking_id}")
                except Exception as e:
                    logger.warning(f"Failed to queue booking confirmation notification: {e}")
                
                logger.info(f"Booking {booking_id} confirmed successfully")
                return booking
                
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error confirming booking {booking_id}: {e}")
            raise
    
    async def cancel_booking(self, booking_id: UUID, reason: Optional[str] = None) -> Booking:
        """
        Cancel a booking and release seats back to inventory.
        
        Args:
            booking_id: ID of the booking to cancel
            reason: Optional cancellation reason
            
        Returns:
            Cancelled booking instance
            
        Raises:
            BookingNotFoundError: When booking is not found
            InvalidBookingStateError: When booking cannot be cancelled
        """
        logger.info(f"Cancelling booking {booking_id}")
        
        try:
            async with self.session.begin():
                # Get booking with related data
                booking = await self._get_booking_with_relations(booking_id)
                
                # Validate booking can be cancelled
                self._validate_booking_cancellation(booking)
                
                # Release seats back to inventory
                await self._release_booking_capacity(booking)
                
                # Update booking status
                booking.status = BookingStatus.CANCELLED
                booking.expires_at = None
                
                # Create booking history entry
                history_details = "Booking cancelled"
                if reason:
                    history_details += f" - Reason: {reason}"
                
                await self._create_booking_history(
                    booking.id,
                    "CANCELLED",
                    history_details
                )
                
                # Notify waitlisted users if seats became available
                await self._notify_waitlist(booking.event_id, booking.quantity)
                
                await self.session.commit()
                
                # Trigger booking cancellation notification
                try:
                    from ..tasks.notification_tasks import send_booking_cancellation_task
                    send_booking_cancellation_task.delay(str(booking_id))
                    logger.info(f"Booking cancellation notification queued for {booking_id}")
                except Exception as e:
                    logger.warning(f"Failed to queue booking cancellation notification: {e}")
                
                logger.info(f"Booking {booking_id} cancelled successfully")
                return booking
                
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error cancelling booking {booking_id}: {e}")
            raise
    
    async def expire_booking(self, booking_id: UUID) -> Booking:
        """
        Expire a booking and release seats back to inventory.
        
        Args:
            booking_id: ID of the booking to expire
            
        Returns:
            Expired booking instance
        """
        logger.info(f"Expiring booking {booking_id}")
        
        try:
            async with self.session.begin():
                # Get booking with related data
                booking = await self._get_booking_with_relations(booking_id)
                
                # Only expire pending bookings
                if booking.status != BookingStatus.PENDING:
                    logger.warning(f"Attempted to expire non-pending booking {booking_id}")
                    return booking
                
                # Release seats back to inventory
                await self._release_booking_capacity(booking)
                
                # Update booking status
                booking.status = BookingStatus.EXPIRED
                
                # Create booking history entry
                await self._create_booking_history(
                    booking.id,
                    "EXPIRED",
                    "Booking expired due to timeout"
                )
                
                # Notify waitlisted users if seats became available
                await self._notify_waitlist(booking.event_id, booking.quantity)
                
                await self.session.commit()
                
                logger.info(f"Booking {booking_id} expired successfully")
                return booking
                
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error expiring booking {booking_id}: {e}")
            raise
    
    async def get_booking(self, booking_id: UUID) -> Optional[Booking]:
        """
        Get a booking by ID with related data.
        
        Args:
            booking_id: ID of the booking to retrieve
            
        Returns:
            Booking instance or None if not found
        """
        try:
            return await self._get_booking_with_relations(booking_id)
        except BookingNotFoundError:
            return None
    
    async def get_user_bookings(
        self,
        user_id: UUID,
        status_filter: Optional[List[BookingStatus]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Booking]:
        """
        Get bookings for a specific user.
        
        Args:
            user_id: ID of the user
            status_filter: Optional list of statuses to filter by
            limit: Maximum number of bookings to return
            offset: Number of bookings to skip
            
        Returns:
            List of booking instances
        """
        query = (
            select(Booking)
            .options(
                selectinload(Booking.event),
                selectinload(Booking.seat_bookings).selectinload(SeatBooking.seat)
            )
            .where(Booking.user_id == user_id)
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        if status_filter:
            query = query.where(Booking.status.in_(status_filter))
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_expired_bookings(self, limit: int = 100) -> List[Booking]:
        """
        Get expired bookings that need to be processed.
        
        Args:
            limit: Maximum number of bookings to return
            
        Returns:
            List of expired booking instances
        """
        query = (
            select(Booking)
            .where(
                and_(
                    Booking.status == BookingStatus.PENDING,
                    Booking.expires_at < datetime.utcnow()
                )
            )
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def search_user_bookings(
        self,
        user_id: UUID,
        query: Optional[str] = None,
        status_filter: Optional[List[BookingStatus]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        min_amount: Optional[Decimal] = None,
        max_amount: Optional[Decimal] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Booking], int]:
        """
        Search and filter user bookings with advanced criteria.
        
        Args:
            user_id: ID of the user
            query: Search query for event name or venue
            status_filter: Optional list of statuses to filter by
            date_from: Filter bookings from this date
            date_to: Filter bookings to this date
            min_amount: Minimum booking amount
            max_amount: Maximum booking amount
            sort_by: Field to sort by
            sort_order: Sort order (asc/desc)
            limit: Maximum number of bookings to return
            offset: Number of bookings to skip
            
        Returns:
            Tuple of (bookings list, total count)
        """
        # Build base query
        base_query = (
            select(Booking)
            .options(
                selectinload(Booking.event),
                selectinload(Booking.seat_bookings).selectinload(SeatBooking.seat)
            )
            .join(Event)
            .where(Booking.user_id == user_id)
        )
        
        # Apply filters
        conditions = []
        
        if query:
            # Search in event name and venue
            search_condition = or_(
                Event.name.ilike(f"%{query}%"),
                Event.venue.ilike(f"%{query}%")
            )
            conditions.append(search_condition)
        
        if status_filter:
            conditions.append(Booking.status.in_(status_filter))
        
        if date_from:
            conditions.append(Booking.created_at >= date_from)
        
        if date_to:
            conditions.append(Booking.created_at <= date_to)
        
        if min_amount:
            conditions.append(Booking.total_amount >= min_amount)
        
        if max_amount:
            conditions.append(Booking.total_amount <= max_amount)
        
        if conditions:
            base_query = base_query.where(and_(*conditions))
        
        # Get total count
        count_query = select(func.count()).select_from(
            base_query.subquery()
        )
        count_result = await self.session.execute(count_query)
        total_count = count_result.scalar()
        
        # Apply sorting
        sort_column = getattr(Booking, sort_by, Booking.created_at)
        if sort_order.lower() == "asc":
            base_query = base_query.order_by(asc(sort_column))
        else:
            base_query = base_query.order_by(desc(sort_column))
        
        # Apply pagination
        base_query = base_query.limit(limit).offset(offset)
        
        result = await self.session.execute(base_query)
        bookings = list(result.scalars().all())
        
        return bookings, total_count
    
    async def get_user_booking_stats(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get booking statistics for a user's dashboard.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Dictionary containing booking statistics
        """
        # Get booking counts by status
        status_query = (
            select(
                Booking.status,
                func.count(Booking.id).label('count'),
                func.sum(Booking.total_amount).label('total_amount')
            )
            .where(Booking.user_id == user_id)
            .group_by(Booking.status)
        )
        
        status_result = await self.session.execute(status_query)
        status_data = {row.status: {'count': row.count, 'total': row.total_amount or Decimal('0')} 
                      for row in status_result}
        
        # Get upcoming events count
        upcoming_query = (
            select(func.count(Booking.id))
            .join(Event)
            .where(
                and_(
                    Booking.user_id == user_id,
                    Booking.status == BookingStatus.CONFIRMED,
                    Event.event_date > datetime.utcnow()
                )
            )
        )
        
        upcoming_result = await self.session.execute(upcoming_query)
        upcoming_count = upcoming_result.scalar() or 0
        
        # Get past events count
        past_query = (
            select(func.count(Booking.id))
            .join(Event)
            .where(
                and_(
                    Booking.user_id == user_id,
                    Booking.status == BookingStatus.CONFIRMED,
                    Event.event_date <= datetime.utcnow()
                )
            )
        )
        
        past_result = await self.session.execute(past_query)
        past_count = past_result.scalar() or 0
        
        # Calculate totals
        total_bookings = sum(data['count'] for data in status_data.values())
        total_spent = sum(data['total'] for data in status_data.values())
        cancelled_count = status_data.get(BookingStatus.CANCELLED, {'count': 0})['count']
        
        return {
            'total_bookings': total_bookings,
            'upcoming_events': upcoming_count,
            'past_events': past_count,
            'cancelled_bookings': cancelled_count,
            'total_spent': total_spent
        }
    
    async def get_categorized_bookings(self, user_id: UUID, limit_per_category: int = 10) -> Dict[str, List[Booking]]:
        """
        Get user bookings categorized by status and event timing.
        
        Args:
            user_id: ID of the user
            limit_per_category: Maximum bookings per category
            
        Returns:
            Dictionary with categorized booking lists
        """
        now = datetime.utcnow()
        
        # Upcoming bookings (confirmed, future events)
        upcoming_query = (
            select(Booking)
            .options(
                selectinload(Booking.event),
                selectinload(Booking.seat_bookings).selectinload(SeatBooking.seat)
            )
            .join(Event)
            .where(
                and_(
                    Booking.user_id == user_id,
                    Booking.status == BookingStatus.CONFIRMED,
                    Event.event_date > now
                )
            )
            .order_by(Event.event_date.asc())
            .limit(limit_per_category)
        )
        
        # Past bookings (confirmed, past events)
        past_query = (
            select(Booking)
            .options(
                selectinload(Booking.event),
                selectinload(Booking.seat_bookings).selectinload(SeatBooking.seat)
            )
            .join(Event)
            .where(
                and_(
                    Booking.user_id == user_id,
                    Booking.status == BookingStatus.CONFIRMED,
                    Event.event_date <= now
                )
            )
            .order_by(Event.event_date.desc())
            .limit(limit_per_category)
        )
        
        # Cancelled bookings
        cancelled_query = (
            select(Booking)
            .options(
                selectinload(Booking.event),
                selectinload(Booking.seat_bookings).selectinload(SeatBooking.seat)
            )
            .where(
                and_(
                    Booking.user_id == user_id,
                    Booking.status == BookingStatus.CANCELLED
                )
            )
            .order_by(Booking.updated_at.desc())
            .limit(limit_per_category)
        )
        
        # Pending bookings
        pending_query = (
            select(Booking)
            .options(
                selectinload(Booking.event),
                selectinload(Booking.seat_bookings).selectinload(SeatBooking.seat)
            )
            .where(
                and_(
                    Booking.user_id == user_id,
                    Booking.status == BookingStatus.PENDING
                )
            )
            .order_by(Booking.created_at.desc())
            .limit(limit_per_category)
        )
        
        # Execute all queries
        upcoming_result = await self.session.execute(upcoming_query)
        past_result = await self.session.execute(past_query)
        cancelled_result = await self.session.execute(cancelled_query)
        pending_result = await self.session.execute(pending_query)
        
        return {
            'upcoming': list(upcoming_result.scalars().all()),
            'past': list(past_result.scalars().all()),
            'cancelled': list(cancelled_result.scalars().all()),
            'pending': list(pending_result.scalars().all())
        }
    
    async def get_booking_history(self, booking_id: UUID) -> List[BookingHistory]:
        """
        Get the complete history for a booking.
        
        Args:
            booking_id: ID of the booking
            
        Returns:
            List of booking history entries
        """
        query = (
            select(BookingHistory)
            .where(BookingHistory.booking_id == booking_id)
            .order_by(BookingHistory.created_at.asc())
        )
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def generate_booking_receipt(self, booking_id: UUID) -> Dict[str, Any]:
        """
        Generate a receipt for a booking.
        
        Args:
            booking_id: ID of the booking
            
        Returns:
            Dictionary containing receipt data
        """
        # Get booking with all related data
        booking = await self._get_booking_with_relations(booking_id)
        
        if not booking:
            raise BookingNotFoundError(f"Booking {booking_id} not found")
        
        # Get user information
        user_query = select(User).where(User.id == booking.user_id)
        user_result = await self.session.execute(user_query)
        user = user_result.scalar_one()
        
        # Generate booking reference
        booking_reference = f"EVT-{booking.id.hex[:8].upper()}"
        
        # Create line items
        line_items = []
        
        if booking.seat_bookings:
            # Individual seat items
            for seat_booking in booking.seat_bookings:
                seat = seat_booking.seat
                line_items.append({
                    'description': f"Seat {seat.section}-{seat.row}-{seat.number}",
                    'quantity': 1,
                    'unit_price': seat.price,
                    'total_price': seat.price
                })
        else:
            # General admission
            unit_price = booking.total_amount / booking.quantity
            line_items.append({
                'description': f"General Admission - {booking.event.name}",
                'quantity': booking.quantity,
                'unit_price': unit_price,
                'total_price': booking.total_amount
            })
        
        # Prepare seat details if applicable
        seat_details = None
        if booking.seat_bookings:
            seat_details = [
                {
                    'section': sb.seat.section,
                    'row': sb.seat.row,
                    'number': sb.seat.number,
                    'price': sb.seat.price
                }
                for sb in booking.seat_bookings
            ]
        
        return {
            'booking_id': booking.id,
            'booking_reference': booking_reference,
            'event_name': booking.event.name,
            'event_date': booking.event.event_date,
            'venue': booking.event.venue,
            'customer_name': f"{user.first_name} {user.last_name}",
            'customer_email': user.email,
            'booking_date': booking.created_at,
            'line_items': line_items,
            'subtotal': booking.total_amount,
            'total_amount': booking.total_amount,
            'payment_status': 'Paid' if booking.status == BookingStatus.CONFIRMED else 'Pending',
            'seat_details': seat_details
        }
    
    # Private helper methods
    
    async def _get_event_with_lock(self, event_id: UUID) -> Event:
        """Get event with optimistic locking."""
        query = select(Event).where(Event.id == event_id)
        result = await self.session.execute(query)
        event = result.scalar_one_or_none()
        
        if not event:
            raise EventNotFoundError(str(event_id))
        
        if not event.is_active:
            raise BookingError("Event is not active")
        
        return event
    
    async def _validate_booking_request(
        self,
        event: Event,
        quantity: int,
        seat_ids: Optional[List[UUID]] = None
    ) -> None:
        """Validate booking request parameters."""
        if quantity <= 0:
            raise BookingError("Quantity must be positive")
        
        if quantity > self.settings.max_booking_quantity:
            raise BookingError(f"Cannot book more than {self.settings.max_booking_quantity} tickets")
        
        if event.event_date < datetime.utcnow():
            raise BookingError("Cannot book tickets for past events")
        
        if seat_ids:
            if len(seat_ids) != quantity:
                raise BookingError("Number of selected seats must match quantity")
            
            if not event.has_seat_selection:
                raise BookingError("Event does not support seat selection")
            
            # Validate seats are available
            await self._validate_seat_availability(seat_ids)
        else:
            # Check general capacity
            if event.available_capacity < quantity:
                raise InsufficientCapacityError(
                    f"Insufficient capacity. Available: {event.available_capacity}, Requested: {quantity}"
                )
    
    async def _validate_seat_availability(self, seat_ids: List[UUID]) -> None:
        """Validate that all specified seats are available."""
        query = (
            select(Seat)
            .where(
                and_(
                    Seat.id.in_(seat_ids),
                    Seat.status == SeatStatus.AVAILABLE
                )
            )
        )
        
        result = await self.session.execute(query)
        available_seats = list(result.scalars().all())
        
        if len(available_seats) != len(seat_ids):
            unavailable_seats = set(seat_ids) - {seat.id for seat in available_seats}
            raise InsufficientCapacityError(f"Seats not available: {unavailable_seats}")
    
    async def _calculate_total_amount(
        self,
        event: Event,
        quantity: int,
        seat_ids: Optional[List[UUID]] = None
    ) -> Decimal:
        """Calculate total booking amount."""
        if seat_ids:
            # Calculate based on individual seat prices
            query = select(Seat.price).where(Seat.id.in_(seat_ids))
            result = await self.session.execute(query)
            seat_prices = list(result.scalars().all())
            return sum(seat_prices)
        else:
            # Use event base price
            return event.price * quantity
    
    async def _reserve_specific_seats(self, booking: Booking, seat_ids: List[UUID]) -> None:
        """Reserve specific seats for a booking."""
        # Update seat status to held
        await self.session.execute(
            update(Seat)
            .where(
                and_(
                    Seat.id.in_(seat_ids),
                    Seat.status == SeatStatus.AVAILABLE
                )
            )
            .values(status=SeatStatus.HELD)
        )
        
        # Create seat booking records
        for seat_id in seat_ids:
            seat_booking = SeatBooking(
                booking_id=booking.id,
                seat_id=seat_id
            )
            self.session.add(seat_booking)
    
    async def _update_event_capacity(self, event: Event, quantity: int) -> None:
        """Update event capacity with optimistic locking."""
        # Update with version check for optimistic locking
        result = await self.session.execute(
            update(Event)
            .where(
                and_(
                    Event.id == event.id,
                    Event.version == event.version,
                    Event.available_capacity >= quantity
                )
            )
            .values(
                available_capacity=Event.available_capacity - quantity,
                version=Event.version + 1
            )
        )
        
        if result.rowcount == 0:
            # Either version mismatch or insufficient capacity
            await self.session.refresh(event)
            if event.available_capacity < quantity:
                raise InsufficientCapacityError("Insufficient capacity")
            else:
                raise ConcurrencyError("Event was modified by another transaction")
    
    async def _get_booking_with_relations(self, booking_id: UUID) -> Booking:
        """Get booking with all related data."""
        query = (
            select(Booking)
            .options(
                selectinload(Booking.event),
                selectinload(Booking.seat_bookings).selectinload(SeatBooking.seat)
            )
            .where(Booking.id == booking_id)
        )
        
        result = await self.session.execute(query)
        booking = result.scalar_one_or_none()
        
        if not booking:
            raise BookingNotFoundError(f"Booking {booking_id} not found")
        
        return booking
    
    def _validate_booking_confirmation(self, booking: Booking) -> None:
        """Validate that booking can be confirmed."""
        if booking.status != BookingStatus.PENDING:
            raise InvalidBookingStateError(f"Cannot confirm booking in {booking.status.value} state")
        
        if booking.is_expired:
            raise BookingExpiredError("Cannot confirm expired booking")
    
    def _validate_booking_cancellation(self, booking: Booking) -> None:
        """Validate that booking can be cancelled."""
        if booking.status not in [BookingStatus.PENDING, BookingStatus.CONFIRMED]:
            raise InvalidBookingStateError(f"Cannot cancel booking in {booking.status.value} state")
    
    async def _release_booking_capacity(self, booking: Booking) -> None:
        """Release booking capacity back to event or seats."""
        if booking.seat_bookings:
            # Release specific seats
            seat_ids = [sb.seat_id for sb in booking.seat_bookings]
            await self.session.execute(
                update(Seat)
                .where(Seat.id.in_(seat_ids))
                .values(status=SeatStatus.AVAILABLE)
            )
        else:
            # Release general capacity
            await self.session.execute(
                update(Event)
                .where(Event.id == booking.event_id)
                .values(
                    available_capacity=Event.available_capacity + booking.quantity,
                    version=Event.version + 1
                )
            )
    
    async def _create_booking_history(
        self,
        booking_id: UUID,
        action: str,
        details: str
    ) -> None:
        """Create a booking history entry."""
        history = BookingHistory(
            booking_id=booking_id,
            action=action,
            details=details
        )
        self.session.add(history)
    
    async def _notify_waitlist(self, event_id: UUID, available_quantity: int) -> None:
        """Notify waitlisted users about available seats."""
        try:
            # Trigger waitlist availability notification task
            from ..tasks.notification_tasks import notify_waitlist_availability_task
            notify_waitlist_availability_task.delay(str(event_id), available_quantity)
            logger.info(f"Waitlist notification queued for event {event_id}, {available_quantity} seats available")
        except Exception as e:
            logger.error(f"Error queuing waitlist notification for event {event_id}: {e}")
            # Don't fail the main operation if waitlist notification fails