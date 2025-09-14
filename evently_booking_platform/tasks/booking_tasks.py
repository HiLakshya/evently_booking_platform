"""
Celery tasks for booking management and expiration handling.
"""

import logging
from datetime import datetime
from typing import List
from uuid import UUID

from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession

from .celery_app import celery_app
from ..database import get_db_session
from ..services.booking_service import BookingService
from ..services.waitlist_service import WaitlistService
from ..models.booking import Booking, BookingStatus

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """Base task class that provides database session management."""
    
    def __init__(self):
        self._session = None
    
    async def get_session(self) -> AsyncSession:
        """Get database session for the task."""
        if self._session is None:
            async with get_db_session() as session:
                self._session = session
                return session
        return self._session


@celery_app.task(bind=True, base=DatabaseTask, name="expire_bookings_task")
def expire_bookings_task(self):
    """
    Periodic task to expire bookings that have exceeded their timeout.
    
    This task runs every minute to identify and expire bookings that have
    passed their expiration time, releasing seats back to inventory.
    """
    import asyncio
    
    async def _expire_bookings():
        try:
            logger.info("Starting booking expiration task")
            
            async with get_db_session() as session:
                booking_service = BookingService(session)
                
                # Get expired bookings
                expired_bookings = await booking_service.get_expired_bookings(limit=100)
                
                if not expired_bookings:
                    logger.info("No expired bookings found")
                    return {"expired_count": 0}
                
                logger.info(f"Found {len(expired_bookings)} expired bookings")
                
                expired_count = 0
                for booking in expired_bookings:
                    try:
                        await booking_service.expire_booking(booking.id)
                        expired_count += 1
                        logger.info(f"Expired booking {booking.id}")
                    except Exception as e:
                        logger.error(f"Failed to expire booking {booking.id}: {e}")
                
                logger.info(f"Successfully expired {expired_count} bookings")
                return {"expired_count": expired_count}
                
        except Exception as e:
            logger.error(f"Error in booking expiration task: {e}")
            raise
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_expire_bookings())
    finally:
        loop.close()


@celery_app.task(bind=True, base=DatabaseTask, name="cleanup_expired_bookings_task")
def cleanup_expired_bookings_task(self):
    """
    Periodic task to clean up old expired bookings.
    
    This task runs every 5 minutes to perform additional cleanup
    on expired bookings, such as archiving old records.
    """
    import asyncio
    
    async def _cleanup_expired_bookings():
        try:
            logger.info("Starting expired bookings cleanup task")
            
            async with get_db_session() as session:
                # This is a placeholder for cleanup logic
                # In a real implementation, you might:
                # - Archive old expired bookings
                # - Send final notifications
                # - Update analytics
                
                logger.info("Expired bookings cleanup completed")
                return {"cleaned_count": 0}
                
        except Exception as e:
            logger.error(f"Error in expired bookings cleanup task: {e}")
            raise
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_cleanup_expired_bookings())
    finally:
        loop.close()


@celery_app.task(bind=True, base=DatabaseTask, name="expire_single_booking_task")
def expire_single_booking_task(self, booking_id: str):
    """
    Task to expire a specific booking.
    
    This task can be scheduled to run at a specific time when a booking
    should expire, providing more precise expiration timing.
    
    Args:
        booking_id: UUID string of the booking to expire
    """
    import asyncio
    
    async def _expire_single_booking():
        try:
            logger.info(f"Expiring specific booking {booking_id}")
            
            async with get_db_session() as session:
                booking_service = BookingService(session)
                
                try:
                    booking = await booking_service.expire_booking(UUID(booking_id))
                    logger.info(f"Successfully expired booking {booking_id}")
                    return {"booking_id": booking_id, "status": "expired"}
                except Exception as e:
                    logger.error(f"Failed to expire booking {booking_id}: {e}")
                    return {"booking_id": booking_id, "status": "failed", "error": str(e)}
                
        except Exception as e:
            logger.error(f"Error in single booking expiration task: {e}")
            raise
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_expire_single_booking())
    finally:
        loop.close()


@celery_app.task(bind=True, base=DatabaseTask, name="process_booking_batch_task")
def process_booking_batch_task(self, booking_ids: List[str], operation: str):
    """
    Task to process a batch of bookings with a specific operation.
    
    This task can handle bulk operations on bookings, such as
    batch expiration or batch confirmation.
    
    Args:
        booking_ids: List of booking UUID strings
        operation: Operation to perform ('expire', 'confirm', etc.)
    """
    import asyncio
    
    async def _process_booking_batch():
        try:
            logger.info(f"Processing batch of {len(booking_ids)} bookings with operation: {operation}")
            
            async with get_db_session() as session:
                booking_service = BookingService(session)
                
                results = []
                for booking_id_str in booking_ids:
                    try:
                        booking_id = UUID(booking_id_str)
                        
                        if operation == "expire":
                            await booking_service.expire_booking(booking_id)
                            results.append({"booking_id": booking_id_str, "status": "success"})
                        else:
                            results.append({"booking_id": booking_id_str, "status": "unsupported_operation"})
                            
                    except Exception as e:
                        logger.error(f"Failed to process booking {booking_id_str}: {e}")
                        results.append({"booking_id": booking_id_str, "status": "failed", "error": str(e)})
                
                success_count = sum(1 for r in results if r["status"] == "success")
                logger.info(f"Successfully processed {success_count}/{len(booking_ids)} bookings")
                
                return {
                    "operation": operation,
                    "total_count": len(booking_ids),
                    "success_count": success_count,
                    "results": results
                }
                
        except Exception as e:
            logger.error(f"Error in booking batch processing task: {e}")
            raise
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_process_booking_batch())
    finally:
        loop.close()


# Utility functions for scheduling tasks

def schedule_booking_expiration(booking_id: UUID, expires_at: datetime):
    """
    Schedule a booking to be expired at a specific time.
    
    Args:
        booking_id: ID of the booking to expire
        expires_at: When the booking should expire
    """
    expire_single_booking_task.apply_async(
        args=[str(booking_id)],
        eta=expires_at
    )
    logger.info(f"Scheduled expiration for booking {booking_id} at {expires_at}")


def schedule_booking_batch_expiration(booking_ids: List[UUID]):
    """
    Schedule a batch of bookings for immediate expiration.
    
    Args:
        booking_ids: List of booking IDs to expire
    """
    process_booking_batch_task.apply_async(
        args=[
            [str(booking_id) for booking_id in booking_ids],
            "expire"
        ]
    )
    logger.info(f"Scheduled batch expiration for {len(booking_ids)} bookings")


@celery_app.task(bind=True, base=DatabaseTask, name="expire_waitlist_notifications_task")
def expire_waitlist_notifications_task(self):
    """
    Periodic task to expire waitlist notifications that haven't been acted upon.
    
    This task runs every hour to identify waitlist entries that were notified
    but haven't been converted to bookings within the timeout period.
    """
    import asyncio
    
    async def _expire_waitlist_notifications():
        try:
            logger.info("Starting waitlist notifications expiration task")
            
            async with get_db_session() as session:
                waitlist_service = WaitlistService(session)
                
                # Expire notifications that have timed out
                expired_entries = await waitlist_service.expire_waitlist_notifications()
                
                if not expired_entries:
                    logger.info("No expired waitlist notifications found")
                    return {"expired_count": 0}
                
                logger.info(f"Expired {len(expired_entries)} waitlist notifications")
                return {"expired_count": len(expired_entries)}
                
        except Exception as e:
            logger.error(f"Error in waitlist notifications expiration task: {e}")
            raise
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_expire_waitlist_notifications())
    finally:
        loop.close()