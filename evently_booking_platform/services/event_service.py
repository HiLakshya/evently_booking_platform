"""
Event service for managing events and their operations.
"""

import hashlib
import logging
from datetime import datetime
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, or_, func, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from evently_booking_platform.models import Event, Booking, BookingStatus
from evently_booking_platform.schemas.event import EventCreate, EventUpdate, EventFilters
from evently_booking_platform.utils.exceptions import (
    EventNotFoundError,
    EventHasBookingsError,
    ValidationError
)
from evently_booking_platform.cache import (
    get_cache, CacheKeyBuilder, CacheTTL, CacheInvalidator
)

logger = logging.getLogger(__name__)


class EventService:
    """Service class for event management operations."""
    
    def __init__(self, db: AsyncSession):
        """Initialize the event service with database session."""
        self.db = db
        self.cache = get_cache()
    
    async def create_event(self, event_data: EventCreate) -> Event:
        """
        Create a new event.
        
        Args:
            event_data: Event creation data
            
        Returns:
            Created event instance
            
        Raises:
            ValidationError: If event data is invalid
        """
        try:
            # Create event with available_capacity equal to total_capacity initially
            event = Event(
                name=event_data.name,
                description=event_data.description,
                venue=event_data.venue,
                event_date=event_data.event_date,
                total_capacity=event_data.total_capacity,
                available_capacity=event_data.total_capacity,  # Initially all seats available
                price=event_data.price,
                has_seat_selection=event_data.has_seat_selection
            )
            
            self.db.add(event)
            await self.db.commit()
            await self.db.refresh(event)
            
            # Invalidate related caches
            await CacheInvalidator.invalidate_event_list_caches()
            
            return event
            
        except IntegrityError as e:
            await self.db.rollback()
            raise ValidationError(f"Failed to create event: {str(e)}")
    
    async def get_event_by_id(self, event_id: UUID) -> Event:
        """
        Get event by ID with caching.
        
        Args:
            event_id: Event UUID
            
        Returns:
            Event instance
            
        Raises:
            EventNotFoundError: If event is not found
        """
        # Try to get from cache first
        cache_key = CacheKeyBuilder.event_detail(str(event_id))
        cached_event = await self.cache.get(cache_key)
        
        if cached_event:
            # Convert cached data back to Event object
            event = Event(**cached_event)
            return event
        
        # Get from database
        result = await self.db.execute(
            select(Event).where(Event.id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise EventNotFoundError(f"Event with ID {event_id} not found")
        
        # Cache the event
        event_dict = {
            "id": str(event.id),
            "name": event.name,
            "description": event.description,
            "venue": event.venue,
            "event_date": event.event_date.isoformat(),
            "total_capacity": event.total_capacity,
            "available_capacity": event.available_capacity,
            "price": float(event.price),
            "has_seat_selection": event.has_seat_selection,
            "is_active": event.is_active,
            "created_at": event.created_at.isoformat(),
            "updated_at": event.updated_at.isoformat(),
            "version": event.version
        }
        await self.cache.set(cache_key, event_dict, CacheTTL.EVENT_DETAIL)
        
        return event
    
    def _create_filters_hash(self, filters: EventFilters) -> str:
        """Create a hash of filters for cache key generation."""
        filters_dict = filters.model_dump()
        # Convert datetime objects to strings for consistent hashing
        for key, value in filters_dict.items():
            if isinstance(value, datetime):
                filters_dict[key] = value.isoformat()
        
        filters_str = str(sorted(filters_dict.items()))
        return hashlib.md5(filters_str.encode()).hexdigest()

    async def get_events(
        self,
        filters: EventFilters,
        page: int = 1,
        size: int = 20
    ) -> Tuple[list[Event], int]:
        """
        Get events with filtering and pagination with caching.
        
        Args:
            filters: Event filtering parameters
            page: Page number (1-based)
            size: Page size
            
        Returns:
            Tuple of (events list, total count)
        """
        # Try to get from cache first
        filters_hash = self._create_filters_hash(filters)
        cache_key = CacheKeyBuilder.event_list(filters_hash, page, size)
        cached_result = await self.cache.get(cache_key)
        
        if cached_result:
            events_data, total = cached_result
            # Convert cached data back to Event objects
            events = [Event(**event_data) for event_data in events_data]
            return events, total
        # Build base query
        conditions = []
        
        # Active events only
        if filters.active_only:
            conditions.append(Event.is_active == True)
        
        # Available capacity filter
        if filters.available_only:
            conditions.append(Event.available_capacity > 0)
        
        # Search in name, description, or venue
        if filters.search:
            search_term = f"%{filters.search}%"
            search_condition = or_(
                Event.name.ilike(search_term),
                Event.description.ilike(search_term),
                Event.venue.ilike(search_term)
            )
            conditions.append(search_condition)
        
        # Venue filter
        if filters.venue:
            conditions.append(Event.venue.ilike(f"%{filters.venue}%"))
        
        # Date range filters
        if filters.date_from:
            conditions.append(Event.event_date >= filters.date_from)
        
        if filters.date_to:
            conditions.append(Event.event_date <= filters.date_to)
        
        # Price range filters
        if filters.min_price is not None:
            conditions.append(Event.price >= filters.min_price)
        
        if filters.max_price is not None:
            conditions.append(Event.price <= filters.max_price)
        
        # Build the where clause
        where_clause = and_(*conditions) if conditions else True
        
        # Get total count
        count_query = select(func.count(Event.id)).where(where_clause)
        count_result = await self.db.execute(count_query)
        total = count_result.scalar()
        
        # Get events with pagination
        offset = (page - 1) * size
        events_query = (
            select(Event)
            .where(where_clause)
            .order_by(Event.event_date)
            .offset(offset)
            .limit(size)
        )
        
        events_result = await self.db.execute(events_query)
        events = events_result.scalars().all()
        
        # Cache the results
        events_data = []
        for event in events:
            event_dict = {
                "id": str(event.id),
                "name": event.name,
                "description": event.description,
                "venue": event.venue,
                "event_date": event.event_date.isoformat(),
                "total_capacity": event.total_capacity,
                "available_capacity": event.available_capacity,
                "price": float(event.price),
                "has_seat_selection": event.has_seat_selection,
                "is_active": event.is_active,
                "created_at": event.created_at.isoformat(),
                "updated_at": event.updated_at.isoformat(),
                "version": event.version
            }
            events_data.append(event_dict)
        
        await self.cache.set(cache_key, (events_data, total), CacheTTL.EVENT_LIST)
        
        return list(events), total
    
    async def update_event(self, event_id: UUID, event_data: EventUpdate) -> Event:
        """
        Update an existing event.
        
        Args:
            event_id: Event UUID
            event_data: Event update data
            
        Returns:
            Updated event instance
            
        Raises:
            EventNotFoundError: If event is not found
            ValidationError: If update data is invalid
        """
        event = await self.get_event_by_id(event_id)
        
        try:
            # Update fields if provided
            update_data = event_data.model_dump(exclude_unset=True)
            
            # Handle capacity updates carefully
            if 'total_capacity' in update_data:
                new_total_capacity = update_data['total_capacity']
                booked_capacity = event.total_capacity - event.available_capacity
                
                # Ensure new capacity can accommodate existing bookings
                if new_total_capacity < booked_capacity:
                    raise ValidationError(
                        f"Cannot reduce capacity below existing bookings. "
                        f"Current bookings: {booked_capacity}, New capacity: {new_total_capacity}"
                    )
                
                # Update available capacity proportionally
                event.available_capacity = new_total_capacity - booked_capacity
                event.total_capacity = new_total_capacity
                update_data.pop('total_capacity')  # Remove from update_data as we handled it manually
            
            # Update other fields
            for field, value in update_data.items():
                if hasattr(event, field):
                    setattr(event, field, value)
            
            # Increment version for optimistic locking
            event.version += 1
            
            await self.db.commit()
            await self.db.refresh(event)
            
            # Invalidate caches for this event
            await CacheInvalidator.invalidate_event_caches(str(event_id))
            
            return event
            
        except IntegrityError as e:
            await self.db.rollback()
            raise ValidationError(f"Failed to update event: {str(e)}")
    
    async def send_event_update_notification(self, event_id: UUID, update_message: str) -> None:
        """
        Send update notification to all users with confirmed bookings for an event.
        
        Args:
            event_id: Event UUID
            update_message: Message describing the update
        """
        try:
            from ..tasks.notification_tasks import send_event_update_task
            send_event_update_task.delay(str(event_id), update_message)
            logger.info(f"Event update notifications queued for event {event_id}")
        except Exception as e:
            logger.warning(f"Failed to queue event update notifications: {e}")
    
    async def delete_event(self, event_id: UUID) -> None:
        """
        Delete an event.
        
        Args:
            event_id: Event UUID
            
        Raises:
            EventNotFoundError: If event is not found
            EventHasBookingsError: If event has active bookings
        """
        event = await self.get_event_by_id(event_id)
        
        # Check if event has any confirmed bookings
        count_query = select(func.count(Booking.id)).where(
            and_(
                Booking.event_id == event_id,
                Booking.status == BookingStatus.CONFIRMED
            )
        )
        count_result = await self.db.execute(count_query)
        confirmed_bookings = count_result.scalar()
        
        if confirmed_bookings > 0:
            raise EventHasBookingsError(
                f"Cannot delete event with {confirmed_bookings} confirmed bookings"
            )
        
        try:
            await self.db.delete(event)
            await self.db.commit()
            
            # Invalidate caches for this event
            await CacheInvalidator.invalidate_event_caches(str(event_id))
            
            # Trigger event cancellation notifications
            try:
                from ..tasks.notification_tasks import send_event_cancellation_task
                send_event_cancellation_task.delay(str(event_id))
                logger.info(f"Event cancellation notifications queued for event {event_id}")
            except Exception as e:
                logger.warning(f"Failed to queue event cancellation notifications: {e}")
            
        except IntegrityError as e:
            await self.db.rollback()
            raise ValidationError(f"Failed to delete event: {str(e)}")
    
    async def search_events(self, search_term: str, limit: int = 10) -> list[Event]:
        """
        Search events by name, description, or venue.
        
        Args:
            search_term: Search term
            limit: Maximum number of results
            
        Returns:
            List of matching events
        """
        search_pattern = f"%{search_term}%"
        
        query = select(Event).where(
            and_(
                Event.is_active == True,
                Event.event_date > datetime.now(),
                or_(
                    Event.name.ilike(search_pattern),
                    Event.description.ilike(search_pattern),
                    Event.venue.ilike(search_pattern)
                )
            )
        ).order_by(Event.event_date).limit(limit)
        
        result = await self.db.execute(query)
        events = result.scalars().all()
        
        return list(events)
    
    async def get_popular_events(self, limit: int = 10) -> list[Event]:
        """
        Get popular events based on booking count with caching.
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List of popular events
        """
        # Try to get from cache first
        cache_key = CacheKeyBuilder.popular_events(limit)
        cached_events = await self.cache.get(cache_key)
        
        if cached_events:
            # Convert cached data back to Event objects
            events = [Event(**event_data) for event_data in cached_events]
            return events
        # Subquery to count confirmed bookings per event
        booking_counts = (
            select(
                Booking.event_id,
                func.count(Booking.id).label('booking_count')
            )
            .where(Booking.status == BookingStatus.CONFIRMED)
            .group_by(Booking.event_id)
            .subquery()
        )
        
        # Join with events and order by booking count
        query = (
            select(Event)
            .join(booking_counts, Event.id == booking_counts.c.event_id)
            .where(
                and_(
                    Event.is_active == True,
                    Event.event_date > datetime.now()
                )
            )
            .order_by(desc(booking_counts.c.booking_count))
            .limit(limit)
        )
        
        result = await self.db.execute(query)
        popular_events = result.scalars().all()
        
        # Cache the results
        events_data = []
        for event in popular_events:
            event_dict = {
                "id": str(event.id),
                "name": event.name,
                "description": event.description,
                "venue": event.venue,
                "event_date": event.event_date.isoformat(),
                "total_capacity": event.total_capacity,
                "available_capacity": event.available_capacity,
                "price": float(event.price),
                "has_seat_selection": event.has_seat_selection,
                "is_active": event.is_active,
                "created_at": event.created_at.isoformat(),
                "updated_at": event.updated_at.isoformat(),
                "version": event.version
            }
            events_data.append(event_dict)
        
        await self.cache.set(cache_key, events_data, CacheTTL.POPULAR_EVENTS)
        
        return list(popular_events)
    
    async def get_upcoming_events(self, limit: int = 10) -> list[Event]:
        """
        Get upcoming events with caching.
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List of upcoming events
        """
        # Try to get from cache first
        cache_key = CacheKeyBuilder.upcoming_events(limit)
        cached_events = await self.cache.get(cache_key)
        
        if cached_events:
            # Convert cached data back to Event objects
            events = [Event(**event_data) for event_data in cached_events]
            return events
        query = select(Event).where(
            and_(
                Event.is_active == True,
                Event.event_date > datetime.now(),
                Event.available_capacity > 0
            )
        ).order_by(Event.event_date).limit(limit)
        
        result = await self.db.execute(query)
        events = result.scalars().all()
        
        # Cache the results
        events_data = []
        for event in events:
            event_dict = {
                "id": str(event.id),
                "name": event.name,
                "description": event.description,
                "venue": event.venue,
                "event_date": event.event_date.isoformat(),
                "total_capacity": event.total_capacity,
                "available_capacity": event.available_capacity,
                "price": float(event.price),
                "has_seat_selection": event.has_seat_selection,
                "is_active": event.is_active,
                "created_at": event.created_at.isoformat(),
                "updated_at": event.updated_at.isoformat(),
                "version": event.version
            }
            events_data.append(event_dict)
        
        await self.cache.set(cache_key, events_data, CacheTTL.UPCOMING_EVENTS)
        
        return list(events)