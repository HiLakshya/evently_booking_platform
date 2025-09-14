"""API endpoints for the Evently Booking Platform."""

from fastapi import APIRouter
from .auth import router as auth_router
from .users import router as users_router
from .events import router as events_router
from .seats import router as seats_router
from .bookings import router as bookings_router
from .waitlist import router as waitlist_router
from .analytics import router as analytics_router
from .advanced_analytics import router as advanced_analytics_router

# Create main API router
api_router = APIRouter(prefix="/api/v1")

# Include all routers
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(events_router)
api_router.include_router(seats_router)
api_router.include_router(bookings_router)
api_router.include_router(waitlist_router)
api_router.include_router(analytics_router)
api_router.include_router(advanced_analytics_router)

__all__ = ["api_router"]