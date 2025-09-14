"""
Celery application configuration for background tasks.
"""

from celery import Celery
from ..config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "evently_booking_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "evently_booking_platform.tasks.booking_tasks",
        "evently_booking_platform.tasks.notification_tasks",
    ]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Periodic tasks configuration
celery_app.conf.beat_schedule = {
    "expire-bookings": {
        "task": "expire_bookings_task",
        "schedule": 60.0,  # Run every minute
    },
    "cleanup-expired-bookings": {
        "task": "cleanup_expired_bookings_task",
        "schedule": 300.0,  # Run every 5 minutes
    },
    "expire-waitlist-notifications": {
        "task": "expire_waitlist_notifications_task",
        "schedule": 3600.0,  # Run every hour
    },
}

celery_app.conf.timezone = "UTC"
