"""
Waitlist API endpoints for managing event waitlists.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..models.waitlist import WaitlistStatus
from ..schemas.waitlist import (
    WaitlistCreate,
    WaitlistResponse,
    WaitlistWithEvent,
    WaitlistStatsResponse
)
from ..services.waitlist_service import (
    WaitlistService,
    WaitlistError,
    WaitlistNotFoundError,
    AlreadyOnWaitlistError,
    EventNotSoldOutError
)
from ..utils.dependencies import get_current_user, get_current_admin_user
from ..models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


@router.post("/", response_model=WaitlistResponse, status_code=status.HTTP_201_CREATED)
async def join_waitlist(
    waitlist_data: WaitlistCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Join the waitlist for a sold-out event.
    
    - **event_id**: ID of the event to join waitlist for
    - **requested_quantity**: Number of tickets requested
    """
    try:
        waitlist_service = WaitlistService(session)
        waitlist_entry = await waitlist_service.join_waitlist(
            user_id=current_user.id,
            event_id=waitlist_data.event_id,
            requested_quantity=waitlist_data.requested_quantity
        )
        
        logger.info(f"User {current_user.id} joined waitlist for event {waitlist_data.event_id}")
        return waitlist_entry
        
    except AlreadyOnWaitlistError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except EventNotSoldOutError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except WaitlistError as e:
        logger.error(f"Error joining waitlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error joining waitlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to join waitlist"
        )


@router.delete("/{event_id}")
async def leave_waitlist(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Leave the waitlist for an event.
    
    - **event_id**: ID of the event to leave waitlist for
    """
    try:
        waitlist_service = WaitlistService(session)
        removed = await waitlist_service.leave_waitlist(
            user_id=current_user.id,
            event_id=event_id
        )
        
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User is not on waitlist for this event"
            )
        
        logger.info(f"User {current_user.id} left waitlist for event {event_id}")
        return {"message": "Successfully left waitlist"}
        
    except WaitlistError as e:
        logger.error(f"Error leaving waitlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error leaving waitlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to leave waitlist"
        )


@router.get("/my-waitlist", response_model=List[WaitlistResponse])
async def get_my_waitlist_entries(
    status: Optional[List[WaitlistStatus]] = Query(None, description="Filter by waitlist status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of entries to return"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get current user's waitlist entries.
    
    - **status**: Optional filter by waitlist status
    - **limit**: Maximum number of entries to return (1-100)
    - **offset**: Number of entries to skip for pagination
    """
    try:
        waitlist_service = WaitlistService(session)
        entries = await waitlist_service.get_user_waitlist_entries(
            user_id=current_user.id,
            status_filter=status,
            limit=limit,
            offset=offset
        )
        
        return entries
        
    except Exception as e:
        logger.error(f"Error getting user waitlist entries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve waitlist entries"
        )


@router.get("/position/{event_id}")
async def get_waitlist_position(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get current user's position in the waitlist for an event.
    
    - **event_id**: ID of the event to check position for
    """
    try:
        waitlist_service = WaitlistService(session)
        position = await waitlist_service.get_user_waitlist_position(
            user_id=current_user.id,
            event_id=event_id
        )
        
        if position is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User is not on waitlist for this event"
            )
        
        return {"position": position}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting waitlist position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get waitlist position"
        )


# Admin endpoints

@router.get("/admin/event/{event_id}", response_model=List[WaitlistResponse])
async def get_event_waitlist(
    event_id: UUID,
    status: Optional[List[WaitlistStatus]] = Query(None, description="Filter by waitlist status"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of entries to return"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    current_admin: User = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get waitlist entries for a specific event (admin only).
    
    - **event_id**: ID of the event
    - **status**: Optional filter by waitlist status
    - **limit**: Maximum number of entries to return (1-500)
    - **offset**: Number of entries to skip for pagination
    """
    try:
        waitlist_service = WaitlistService(session)
        entries = await waitlist_service.get_event_waitlist(
            event_id=event_id,
            status_filter=status,
            limit=limit,
            offset=offset
        )
        
        return entries
        
    except Exception as e:
        logger.error(f"Error getting event waitlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve event waitlist"
        )


@router.get("/admin/stats/{event_id}", response_model=WaitlistStatsResponse)
async def get_waitlist_stats(
    event_id: UUID,
    current_admin: User = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get waitlist statistics for an event (admin only).
    
    - **event_id**: ID of the event
    """
    try:
        waitlist_service = WaitlistService(session)
        stats = await waitlist_service.get_waitlist_stats(event_id)
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting waitlist stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve waitlist statistics"
        )


@router.post("/admin/notify/{event_id}")
async def notify_waitlist(
    event_id: UUID,
    available_quantity: int = Query(..., gt=0, description="Number of available seats"),
    current_admin: User = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Manually notify waitlisted users about available seats (admin only).
    
    - **event_id**: ID of the event
    - **available_quantity**: Number of seats that became available
    """
    try:
        waitlist_service = WaitlistService(session)
        notified_entries = await waitlist_service.notify_waitlist(
            event_id=event_id,
            available_quantity=available_quantity
        )
        
        logger.info(f"Admin {current_admin.id} manually notified waitlist for event {event_id}")
        return {
            "message": f"Notified {len(notified_entries)} waitlist entries",
            "notified_count": len(notified_entries)
        }
        
    except WaitlistError as e:
        logger.error(f"Error notifying waitlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error notifying waitlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to notify waitlist"
        )