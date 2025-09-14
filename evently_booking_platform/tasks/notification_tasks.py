"""
Celery tasks for notification management.
"""

import asyncio
import logging
from uuid import UUID
from typing import List

from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .celery_app import celery_app
from ..database import get_db_session
from ..services.notification_service import NotificationService
from ..services.waitlist_service import WaitlistService
from ..models.waitlist import Waitlist, WaitlistStatus

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


@celery_app.task(bind=True, base=DatabaseTask, name="send_booking_confirmation_task")
def send_booking_confirmation_task(self, booking_id: str):
    """
    Task to send booking confirmation notification.
    
    Args:
        booking_id: ID of the confirmed booking
    """
    import asyncio
    
    async def _send_confirmation():
        try:
            logger.info(f"Sending booking confirmation for {booking_id}")
            
            async with get_db_session() as session:
                notification_service = NotificationService(session)
                success = await notification_service.send_booking_confirmation(UUID(booking_id))
                
                if success:
                    logger.info(f"Booking confirmation sent successfully for {booking_id}")
                    return {"booking_id": booking_id, "status": "sent"}
                else:
                    logger.error(f"Failed to send booking confirmation for {booking_id}")
                    return {"booking_id": booking_id, "status": "failed"}
                    
        except Exception as e:
            logger.error(f"Error in booking confirmation task: {e}")
            return {"booking_id": booking_id, "status": "error", "error": str(e)}
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_send_confirmation())
    finally:
        loop.close()


@celery_app.task(bind=True, base=DatabaseTask, name="send_booking_cancellation_task")
def send_booking_cancellation_task(self, booking_id: str):
    """
    Task to send booking cancellation notification.
    
    Args:
        booking_id: ID of the cancelled booking
    """
    import asyncio
    
    async def _send_cancellation():
        try:
            logger.info(f"Sending booking cancellation for {booking_id}")
            
            async with get_db_session() as session:
                notification_service = NotificationService(session)
                success = await notification_service.send_booking_cancellation(UUID(booking_id))
                
                if success:
                    logger.info(f"Booking cancellation sent successfully for {booking_id}")
                    return {"booking_id": booking_id, "status": "sent"}
                else:
                    logger.error(f"Failed to send booking cancellation for {booking_id}")
                    return {"booking_id": booking_id, "status": "failed"}
                    
        except Exception as e:
            logger.error(f"Error in booking cancellation task: {e}")
            return {"booking_id": booking_id, "status": "error", "error": str(e)}
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_send_cancellation())
    finally:
        loop.close()


@celery_app.task(bind=True, base=DatabaseTask, name="notify_waitlist_availability_task")
def notify_waitlist_availability_task(self, event_id: str, available_quantity: int):
    """
    Task to notify waitlisted users about seat availability.
    
    Args:
        event_id: ID of the event with available seats
        available_quantity: Number of seats that became available
    """
    import asyncio
    
    async def _notify_waitlist():
        try:
            logger.info(f"Notifying waitlist for event {event_id}, {available_quantity} seats available")
            
            async with get_db_session() as session:
                waitlist_service = WaitlistService(session)
                notification_service = NotificationService(session)
                
                # Get next waitlisted users to notify
                waitlist_entries = await waitlist_service.get_next_waitlist_entries(
                    UUID(event_id), 
                    limit=available_quantity
                )
                
                if not waitlist_entries:
                    logger.info(f"No waitlist entries found for event {event_id}")
                    return {
                        "event_id": event_id,
                        "available_quantity": available_quantity,
                        "notified_count": 0,
                        "status": "no_waitlist_entries"
                    }
                
                notified_count = 0
                for entry in waitlist_entries:
                    try:
                        # Update waitlist status to notified
                        await waitlist_service.update_waitlist_status(
                            entry.id, 
                            WaitlistStatus.NOTIFIED
                        )
                        
                        # Send notification
                        success = await notification_service.send_waitlist_availability_notification(
                            entry.id, 
                            available_quantity
                        )
                        
                        if success:
                            notified_count += 1
                            logger.info(f"Waitlist notification sent to user {entry.user_id}")
                        else:
                            logger.error(f"Failed to send waitlist notification to user {entry.user_id}")
                            
                    except Exception as e:
                        logger.error(f"Error notifying waitlist entry {entry.id}: {e}")
                
                logger.info(f"Notified {notified_count} users from waitlist for event {event_id}")
                return {
                    "event_id": event_id,
                    "available_quantity": available_quantity,
                    "notified_count": notified_count,
                    "status": "completed"
                }
                
        except Exception as e:
            logger.error(f"Error in waitlist notification task: {e}")
            return {
                "event_id": event_id,
                "available_quantity": available_quantity,
                "status": "error",
                "error": str(e)
            }
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_notify_waitlist())
    finally:
        loop.close()


@celery_app.task(bind=True, base=DatabaseTask, name="send_event_cancellation_task")
def send_event_cancellation_task(self, event_id: str):
    """
    Task to send event cancellation notifications to all booked users.
    
    Args:
        event_id: ID of the cancelled event
    """
    import asyncio
    
    async def _send_event_cancellation():
        try:
            logger.info(f"Sending event cancellation notifications for event {event_id}")
            
            async with get_db_session() as session:
                notification_service = NotificationService(session)
                sent_count = await notification_service.send_event_cancellation_notification(UUID(event_id))
                
                logger.info(f"Sent {sent_count} event cancellation notifications for event {event_id}")
                return {
                    "event_id": event_id,
                    "sent_count": sent_count,
                    "status": "completed"
                }
                
        except Exception as e:
            logger.error(f"Error in event cancellation task: {e}")
            return {
                "event_id": event_id,
                "status": "error",
                "error": str(e)
            }
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_send_event_cancellation())
    finally:
        loop.close()


@celery_app.task(bind=True, base=DatabaseTask, name="send_event_update_task")
def send_event_update_task(self, event_id: str, update_message: str):
    """
    Task to send event update notifications to all booked users.
    
    Args:
        event_id: ID of the updated event
        update_message: Message describing the update
    """
    import asyncio
    
    async def _send_event_update():
        try:
            logger.info(f"Sending event update notifications for event {event_id}")
            
            async with get_db_session() as session:
                notification_service = NotificationService(session)
                sent_count = await notification_service.send_event_update_notification(
                    UUID(event_id), 
                    update_message
                )
                
                logger.info(f"Sent {sent_count} event update notifications for event {event_id}")
                return {
                    "event_id": event_id,
                    "update_message": update_message,
                    "sent_count": sent_count,
                    "status": "completed"
                }
                
        except Exception as e:
            logger.error(f"Error in event update task: {e}")
            return {
                "event_id": event_id,
                "update_message": update_message,
                "status": "error",
                "error": str(e)
            }
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_send_event_update())
    finally:
        loop.close()


@celery_app.task(bind=True, base=DatabaseTask, name="send_bulk_notifications_task")
def send_bulk_notifications_task(self, notification_type: str, data_list: List[dict]):
    """
    Task to send bulk notifications of a specific type.
    
    Args:
        notification_type: Type of notification ('booking_confirmation', 'booking_cancellation', etc.)
        data_list: List of data dictionaries for each notification
    """
    import asyncio
    
    async def _send_bulk_notifications():
        try:
            logger.info(f"Sending {len(data_list)} bulk notifications of type {notification_type}")
            
            async with get_db_session() as session:
                notification_service = NotificationService(session)
                
                sent_count = 0
                failed_count = 0
                
                for data in data_list:
                    try:
                        success = False
                        
                        if notification_type == "booking_confirmation":
                            success = await notification_service.send_booking_confirmation(UUID(data["booking_id"]))
                        elif notification_type == "booking_cancellation":
                            success = await notification_service.send_booking_cancellation(UUID(data["booking_id"]))
                        elif notification_type == "waitlist_availability":
                            success = await notification_service.send_waitlist_availability_notification(
                                UUID(data["waitlist_id"]), 
                                data["available_quantity"]
                            )
                        
                        if success:
                            sent_count += 1
                        else:
                            failed_count += 1
                            
                    except Exception as e:
                        logger.error(f"Error sending bulk notification: {e}")
                        failed_count += 1
                
                logger.info(f"Bulk notifications completed: {sent_count} sent, {failed_count} failed")
                return {
                    "notification_type": notification_type,
                    "total_count": len(data_list),
                    "sent_count": sent_count,
                    "failed_count": failed_count,
                    "status": "completed"
                }
                
        except Exception as e:
            logger.error(f"Error in bulk notifications task: {e}")
            return {
                "notification_type": notification_type,
                "total_count": len(data_list),
                "status": "error",
                "error": str(e)
            }
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_send_bulk_notifications())
    finally:
        loop.close()