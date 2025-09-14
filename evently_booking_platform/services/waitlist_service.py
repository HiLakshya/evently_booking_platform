"""
Waitlist service for managing event waitlists and notifications.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy import select, update, delete, and_, or_, func, desc, asc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.waitlist import Waitlist, WaitlistStatus
from ..models.event import Event
from ..models.user import User
from ..models.booking import Booking, BookingStatus
from ..config import get_settings
try:
    from ..tasks.notification_tasks import notify_waitlist_availability_task
except ImportError:
    # Celery not available, use a mock function for testing
    def notify_waitlist_availability_task(*args, **kwargs):
        class MockTask:
            def delay(self, *args, **kwargs):
                return {"status": "mocked"}
        return MockTask()

logger = logging.getLogger(__name__)


class WaitlistError(Exception):
    """Base exception for waitlist-related errors."""
    pass


class WaitlistNotFoundError(WaitlistError):
    """Raised when a waitlist entry is not found."""
    pass


class AlreadyOnWaitlistError(WaitlistError):
    """Raised when user is already on waitlist for an event."""
    pass


class EventNotSoldOutError(WaitlistError):
    """Raised when trying to join waitlist for event that's not sold out."""
    pass


class WaitlistService:
    """Service for managing event waitlists."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
    
    async def join_waitlist(
        self,
        user_id: UUID,
        event_id: UUID,
        requested_quantity: int
    ) -> Waitlist:
        """
        Add a user to the waitlist for an event.
        
        Args:
            user_id: ID of the user joining the waitlist
            event_id: ID of the event to join waitlist for
            requested_quantity: Number of tickets requested
            
        Returns:
            Created waitlist entry
            
        Raises:
            AlreadyOnWaitlistError: When user is already on waitlist
            EventNotSoldOutError: When event is not sold out
            WaitlistError: For other waitlist-related errors
        """
        logger.info(f"User {user_id} joining waitlist for event {event_id}, quantity {requested_quantity}")
        
        try:
            # Check if we're already in a transaction
            if self.session.in_transaction():
                # Use existing transaction
                # Check if event exists and is sold out
                event = await self._get_event(event_id)
                
                # For events with available capacity, don't allow waitlist joining
                if event.available_capacity >= requested_quantity:
                    raise EventNotSoldOutError("Event has available capacity. Please book directly.")
                
                # Check if user is already on waitlist for this event
                existing_entry = await self._get_user_waitlist_entry(user_id, event_id)
                if existing_entry:
                    raise AlreadyOnWaitlistError("User is already on waitlist for this event")
                
                # Get next position in queue
                next_position = await self._get_next_waitlist_position(event_id)
                
                # Create waitlist entry
                waitlist_entry = Waitlist(
                    user_id=user_id,
                    event_id=event_id,
                    requested_quantity=requested_quantity,
                    position=next_position,
                    status=WaitlistStatus.ACTIVE
                )
                
                self.session.add(waitlist_entry)
                await self.session.flush()  # Flush to get the ID
                
                logger.info(f"User {user_id} added to waitlist at position {next_position}")
                return waitlist_entry
            else:
                # Start new transaction
                async with self.session.begin():
                    # Check if event exists and is sold out
                    event = await self._get_event(event_id)
                    
                    # For events with available capacity, don't allow waitlist joining
                    if event.available_capacity >= requested_quantity:
                        raise EventNotSoldOutError("Event has available capacity. Please book directly.")
                    
                    # Check if user is already on waitlist for this event
                    existing_entry = await self._get_user_waitlist_entry(user_id, event_id)
                    if existing_entry:
                        raise AlreadyOnWaitlistError("User is already on waitlist for this event")
                    
                    # Get next position in queue
                    next_position = await self._get_next_waitlist_position(event_id)
                    
                    # Create waitlist entry
                    waitlist_entry = Waitlist(
                        user_id=user_id,
                        event_id=event_id,
                        requested_quantity=requested_quantity,
                        position=next_position,
                        status=WaitlistStatus.ACTIVE
                    )
                    
                    self.session.add(waitlist_entry)
                    await self.session.commit()
                    
                    logger.info(f"User {user_id} added to waitlist at position {next_position}")
                    return waitlist_entry
                
        except IntegrityError as e:
            await self.session.rollback()
            if "uq_waitlist_user_event" in str(e):
                raise AlreadyOnWaitlistError("User is already on waitlist for this event")
            logger.error(f"Database integrity error joining waitlist: {e}")
            raise WaitlistError("Failed to join waitlist due to data conflict")
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error joining waitlist: {e}")
            raise
    
    async def leave_waitlist(self, user_id: UUID, event_id: UUID) -> bool:
        """
        Remove a user from the waitlist for an event.
        
        Args:
            user_id: ID of the user leaving the waitlist
            event_id: ID of the event to leave waitlist for
            
        Returns:
            True if user was removed, False if not on waitlist
        """
        logger.info(f"User {user_id} leaving waitlist for event {event_id}")
        
        try:
            async with self.session.begin():
                # Find the waitlist entry
                waitlist_entry = await self._get_user_waitlist_entry(user_id, event_id)
                if not waitlist_entry:
                    return False
                
                # Store position for reordering
                removed_position = waitlist_entry.position
                
                # Delete the waitlist entry
                await self.session.delete(waitlist_entry)
                
                # Reorder remaining waitlist entries
                await self._reorder_waitlist_after_removal(event_id, removed_position)
                
                await self.session.commit()
                
                logger.info(f"User {user_id} removed from waitlist")
                return True
                
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error leaving waitlist: {e}")
            raise WaitlistError(f"Failed to leave waitlist: {str(e)}")
    
    async def notify_waitlist(self, event_id: UUID, available_quantity: int) -> List[Waitlist]:
        """
        Notify waitlisted users about available seats.
        
        Args:
            event_id: ID of the event with available seats
            available_quantity: Number of seats that became available
            
        Returns:
            List of waitlist entries that were notified
        """
        logger.info(f"Notifying waitlist for event {event_id}, {available_quantity} seats available")
        
        try:
            async with self.session.begin():
                # Get active waitlist entries in order
                waitlist_entries = await self._get_active_waitlist_entries(event_id)
                
                notified_entries = []
                remaining_quantity = available_quantity
                
                for entry in waitlist_entries:
                    if remaining_quantity <= 0:
                        break
                    
                    # Check if we can satisfy this waitlist entry
                    if entry.requested_quantity <= remaining_quantity:
                        # Update status to notified
                        entry.status = WaitlistStatus.NOTIFIED
                        notified_entries.append(entry)
                        remaining_quantity -= entry.requested_quantity
                        
                        # Send notification task
                        try:
                            notify_waitlist_availability_task.delay(
                                str(event_id),
                                entry.requested_quantity
                            )
                        except Exception as e:
                            logger.warning(f"Failed to send notification task: {e}")
                        
                        logger.info(f"Notified waitlist entry {entry.id} for {entry.requested_quantity} seats")
                
                await self.session.commit()
                
                logger.info(f"Notified {len(notified_entries)} waitlist entries")
                return notified_entries
                
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error notifying waitlist: {e}")
            raise WaitlistError(f"Failed to notify waitlist: {str(e)}")
    
    async def convert_waitlist_to_booking(
        self,
        waitlist_id: UUID,
        booking_id: UUID
    ) -> Waitlist:
        """
        Mark a waitlist entry as converted when user successfully books.
        
        Args:
            waitlist_id: ID of the waitlist entry
            booking_id: ID of the successful booking
            
        Returns:
            Updated waitlist entry
        """
        logger.info(f"Converting waitlist entry {waitlist_id} to booking {booking_id}")
        
        try:
            async with self.session.begin():
                # Get waitlist entry
                waitlist_entry = await self._get_waitlist_entry(waitlist_id)
                
                # Update status to converted
                waitlist_entry.status = WaitlistStatus.CONVERTED
                
                # Reorder remaining waitlist entries
                await self._reorder_waitlist_after_removal(
                    waitlist_entry.event_id,
                    waitlist_entry.position
                )
                
                await self.session.commit()
                
                logger.info(f"Waitlist entry {waitlist_id} converted successfully")
                return waitlist_entry
                
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error converting waitlist entry: {e}")
            raise
    
    async def expire_waitlist_notifications(self) -> List[Waitlist]:
        """
        Expire waitlist notifications that haven't been acted upon.
        
        Returns:
            List of expired waitlist entries
        """
        logger.info("Expiring waitlist notifications")
        
        try:
            async with self.session.begin():
                # Calculate expiration time
                expiration_time = datetime.utcnow() - timedelta(
                    hours=self.settings.waitlist_notification_timeout_hours
                )
                
                # Find notified entries that should expire
                query = (
                    select(Waitlist)
                    .where(
                        and_(
                            Waitlist.status == WaitlistStatus.NOTIFIED,
                            Waitlist.updated_at < expiration_time
                        )
                    )
                )
                
                result = await self.session.execute(query)
                expired_entries = list(result.scalars().all())
                
                # Update status to expired and reorder
                for entry in expired_entries:
                    entry.status = WaitlistStatus.EXPIRED
                    
                    # Move to end of queue with new position
                    new_position = await self._get_next_waitlist_position(entry.event_id)
                    entry.position = new_position
                    entry.status = WaitlistStatus.ACTIVE  # Back to active status
                
                await self.session.commit()
                
                logger.info(f"Expired {len(expired_entries)} waitlist notifications")
                return expired_entries
                
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error expiring waitlist notifications: {e}")
            raise WaitlistError(f"Failed to expire notifications: {str(e)}")
    
    async def get_user_waitlist_entries(
        self,
        user_id: UUID,
        status_filter: Optional[List[WaitlistStatus]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Waitlist]:
        """
        Get waitlist entries for a specific user.
        
        Args:
            user_id: ID of the user
            status_filter: Optional list of statuses to filter by
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            
        Returns:
            List of waitlist entries
        """
        query = (
            select(Waitlist)
            .options(selectinload(Waitlist.event))
            .where(Waitlist.user_id == user_id)
            .order_by(Waitlist.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        if status_filter:
            query = query.where(Waitlist.status.in_(status_filter))
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_event_waitlist(
        self,
        event_id: UUID,
        status_filter: Optional[List[WaitlistStatus]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Waitlist]:
        """
        Get waitlist entries for a specific event.
        
        Args:
            event_id: ID of the event
            status_filter: Optional list of statuses to filter by
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            
        Returns:
            List of waitlist entries ordered by position
        """
        query = (
            select(Waitlist)
            .options(selectinload(Waitlist.user))
            .where(Waitlist.event_id == event_id)
            .order_by(Waitlist.position.asc())
            .limit(limit)
            .offset(offset)
        )
        
        if status_filter:
            query = query.where(Waitlist.status.in_(status_filter))
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_waitlist_stats(self, event_id: UUID) -> Dict[str, Any]:
        """
        Get waitlist statistics for an event.
        
        Args:
            event_id: ID of the event
            
        Returns:
            Dictionary containing waitlist statistics
        """
        # Get counts by status
        status_query = (
            select(
                Waitlist.status,
                func.count(Waitlist.id).label('count'),
                func.avg(Waitlist.position).label('avg_position')
            )
            .where(Waitlist.event_id == event_id)
            .group_by(Waitlist.status)
        )
        
        status_result = await self.session.execute(status_query)
        status_data = {row.status: {'count': row.count, 'avg_position': row.avg_position or 0} 
                      for row in status_result}
        
        # Calculate totals
        total_waitlisted = sum(data['count'] for data in status_data.values())
        active_waitlisted = status_data.get(WaitlistStatus.ACTIVE, {'count': 0})['count']
        notified_count = status_data.get(WaitlistStatus.NOTIFIED, {'count': 0})['count']
        converted_count = status_data.get(WaitlistStatus.CONVERTED, {'count': 0})['count']
        
        # Calculate average position for active entries
        active_avg_position = status_data.get(WaitlistStatus.ACTIVE, {'avg_position': 0})['avg_position']
        
        # Estimate wait time (simplified calculation)
        estimated_wait_time = None
        if active_waitlisted > 0:
            # Rough estimate: assume 1 booking per hour becomes available
            estimated_wait_time = int(active_avg_position)
        
        return {
            'total_waitlisted': total_waitlisted,
            'active_waitlisted': active_waitlisted,
            'notified_count': notified_count,
            'converted_count': converted_count,
            'average_position': active_avg_position,
            'estimated_wait_time_hours': estimated_wait_time
        }
    
    async def get_user_waitlist_position(self, user_id: UUID, event_id: UUID) -> Optional[int]:
        """
        Get a user's position in the waitlist for an event.
        
        Args:
            user_id: ID of the user
            event_id: ID of the event
            
        Returns:
            Position in waitlist or None if not on waitlist
        """
        entry = await self._get_user_waitlist_entry(user_id, event_id)
        return entry.position if entry else None
    
    # Private helper methods
    
    async def _get_event(self, event_id: UUID) -> Event:
        """Get event by ID."""
        query = select(Event).where(Event.id == event_id)
        result = await self.session.execute(query)
        event = result.scalar_one_or_none()
        
        if not event:
            raise WaitlistError(f"Event {event_id} not found")
        
        if not event.is_active:
            raise WaitlistError("Event is not active")
        
        return event
    
    async def _get_user_waitlist_entry(self, user_id: UUID, event_id: UUID) -> Optional[Waitlist]:
        """Get user's waitlist entry for an event."""
        query = (
            select(Waitlist)
            .where(
                and_(
                    Waitlist.user_id == user_id,
                    Waitlist.event_id == event_id,
                    Waitlist.status.in_([WaitlistStatus.ACTIVE, WaitlistStatus.NOTIFIED])
                )
            )
        )
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def _get_waitlist_entry(self, waitlist_id: UUID) -> Waitlist:
        """Get waitlist entry by ID."""
        query = select(Waitlist).where(Waitlist.id == waitlist_id)
        result = await self.session.execute(query)
        entry = result.scalar_one_or_none()
        
        if not entry:
            raise WaitlistNotFoundError(f"Waitlist entry {waitlist_id} not found")
        
        return entry
    
    async def _get_next_waitlist_position(self, event_id: UUID) -> int:
        """Get the next position in the waitlist queue."""
        query = (
            select(func.max(Waitlist.position))
            .where(Waitlist.event_id == event_id)
        )
        
        result = await self.session.execute(query)
        max_position = result.scalar()
        
        return (max_position or 0) + 1
    
    async def _get_active_waitlist_entries(self, event_id: UUID) -> List[Waitlist]:
        """Get active waitlist entries ordered by position."""
        query = (
            select(Waitlist)
            .where(
                and_(
                    Waitlist.event_id == event_id,
                    Waitlist.status == WaitlistStatus.ACTIVE
                )
            )
            .order_by(Waitlist.position.asc())
        )
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def _reorder_waitlist_after_removal(self, event_id: UUID, removed_position: int) -> None:
        """Reorder waitlist positions after an entry is removed."""
        # Update positions for entries that were after the removed one
        await self.session.execute(
            update(Waitlist)
            .where(
                and_(
                    Waitlist.event_id == event_id,
                    Waitlist.position > removed_position,
                    Waitlist.status.in_([WaitlistStatus.ACTIVE, WaitlistStatus.NOTIFIED])
                )
            )
            .values(position=Waitlist.position - 1)
        )