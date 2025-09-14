"""
Pydantic schemas for waitlist management.
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING, ForwardRef
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from ..models.waitlist import WaitlistStatus

if TYPE_CHECKING:
    from .event import EventResponse
    from .auth import UserResponse

# Forward references for proper schema resolution
EventResponse = ForwardRef('EventResponse')
UserResponse = ForwardRef('UserResponse')


class WaitlistBase(BaseModel):
    """Base schema for waitlist entries."""
    requested_quantity: int = Field(..., gt=0, description="Number of tickets requested")


class WaitlistCreate(WaitlistBase):
    """Schema for creating a waitlist entry."""
    event_id: UUID = Field(..., description="ID of the event to join waitlist for")


class WaitlistUpdate(BaseModel):
    """Schema for updating a waitlist entry."""
    status: Optional[WaitlistStatus] = Field(None, description="New status for waitlist entry")


class WaitlistResponse(WaitlistBase):
    """Schema for waitlist entry responses."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    event_id: UUID
    position: int = Field(..., description="Position in the waitlist queue")
    status: WaitlistStatus
    created_at: datetime
    updated_at: datetime


class WaitlistWithEvent(WaitlistResponse):
    """Schema for waitlist entry with event details."""
    event: EventResponse


class WaitlistWithUser(WaitlistResponse):
    """Schema for waitlist entry with user details."""
    user: UserResponse


class WaitlistNotificationResponse(BaseModel):
    """Schema for waitlist notification responses."""
    waitlist_id: UUID
    user_id: UUID
    event_id: UUID
    available_quantity: int
    notification_sent: bool
    expires_at: datetime = Field(..., description="When the booking opportunity expires")


class WaitlistStatsResponse(BaseModel):
    """Schema for waitlist statistics."""
    total_waitlisted: int
    active_waitlisted: int
    notified_count: int
    converted_count: int
    average_position: float
    estimated_wait_time_hours: Optional[int] = Field(None, description="Estimated wait time in hours")