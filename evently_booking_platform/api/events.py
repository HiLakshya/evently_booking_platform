"""
Event management API endpoints.
"""

from typing import List
from uuid import UUID
import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from evently_booking_platform.models import User
from evently_booking_platform.schemas.event import (
    EventCreate,
    EventUpdate,
    EventResponse,
    EventListResponse,
    EventFilters
)
from evently_booking_platform.services.event_service import EventService
from evently_booking_platform.utils.dependencies import get_db, get_current_user, get_current_admin_user
from evently_booking_platform.utils.exceptions import (
    EventNotFoundError,
    EventHasBookingsError,
    ValidationError
)


router = APIRouter(prefix="/events", tags=["events"])


def get_event_service(db: AsyncSession = Depends(get_db)) -> EventService:
    """Dependency to get event service instance."""
    return EventService(db)


@router.get("/", response_model=EventListResponse)
async def list_events(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    search: str = Query(None, description="Search in event name, description, or venue"),
    venue: str = Query(None, description="Filter by venue"),
    date_from: str = Query(None, description="Filter events from this date (ISO format)"),
    date_to: str = Query(None, description="Filter events until this date (ISO format)"),
    min_price: float = Query(None, ge=0, description="Minimum ticket price"),
    max_price: float = Query(None, ge=0, description="Maximum ticket price"),
    available_only: bool = Query(True, description="Show only events with available capacity"),
    active_only: bool = Query(True, description="Show only active events"),
    event_service: EventService = Depends(get_event_service)
):
    """
    Get list of events with filtering and pagination.
    
    This endpoint supports various filtering options:
    - Search by name, description, or venue
    - Filter by venue, date range, price range
    - Show only available or active events
    """
    try:
        # Parse date strings if provided
        from datetime import datetime
        parsed_date_from = None
        parsed_date_to = None
        
        if date_from:
            try:
                parsed_date_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date_from format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )
        
        if date_to:
            try:
                parsed_date_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date_to format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )
        
        # Create filters object
        filters = EventFilters(
            search=search,
            venue=venue,
            date_from=parsed_date_from,
            date_to=parsed_date_to,
            min_price=min_price,
            max_price=max_price,
            available_only=available_only,
            active_only=active_only
        )
        
        events, total = await event_service.get_events(filters, page, size)
        pages = math.ceil(total / size) if total > 0 else 1
        
        return EventListResponse(
            events=events,
            total=total,
            page=page,
            size=size,
            pages=pages
        )
        
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event_data: EventCreate,
    current_user: User = Depends(get_current_admin_user),
    event_service: EventService = Depends(get_event_service)
):
    """
    Create a new event.
    
    Only admin users can create events.
    """
    try:
        event = await event_service.create_event(event_data)
        return event
        
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: UUID,
    event_service: EventService = Depends(get_event_service)
):
    """
    Get event details by ID.
    """
    try:
        event = await event_service.get_event_by_id(event_id)
        return event
        
    except EventNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.put("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: UUID,
    event_data: EventUpdate,
    current_user: User = Depends(get_current_admin_user),
    event_service: EventService = Depends(get_event_service)
):
    """
    Update an existing event.
    
    Only admin users can update events.
    """
    try:
        event = await event_service.update_event(event_id, event_data)
        return event
        
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
            detail="Internal server error"
        )


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: UUID,
    current_user: User = Depends(get_current_admin_user),
    event_service: EventService = Depends(get_event_service)
):
    """
    Delete an event.
    
    Only admin users can delete events.
    Events with confirmed bookings cannot be deleted.
    """
    try:
        await event_service.delete_event(event_id)
        
    except EventNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except EventHasBookingsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/search/{search_term}", response_model=List[EventResponse])
async def search_events(
    search_term: str,
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results"),
    event_service: EventService = Depends(get_event_service)
):
    """
    Search events by name, description, or venue.
    """
    try:
        events = await event_service.search_events(search_term, limit)
        return events
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/popular/list", response_model=List[EventResponse])
async def get_popular_events(
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results"),
    event_service: EventService = Depends(get_event_service)
):
    """
    Get popular events based on booking count.
    """
    try:
        events = await event_service.get_popular_events(limit)
        return events
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/upcoming/list", response_model=List[EventResponse])
async def get_upcoming_events(
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results"),
    event_service: EventService = Depends(get_event_service)
):
    """
    Get upcoming events with available capacity.
    """
    try:
        events = await event_service.get_upcoming_events(limit)
        return events
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )