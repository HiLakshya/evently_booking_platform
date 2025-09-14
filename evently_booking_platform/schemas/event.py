"""
Event schemas for request/response validation.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


class EventBase(BaseModel):
    """Base event schema with common fields."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Event name")
    description: Optional[str] = Field(None, description="Event description")
    venue: str = Field(..., min_length=1, max_length=255, description="Event venue")
    event_date: datetime = Field(..., description="Event date and time")
    total_capacity: int = Field(..., gt=0, description="Total event capacity")
    price: Decimal = Field(..., ge=0, description="Event ticket price")
    has_seat_selection: bool = Field(default=False, description="Whether event has seat selection")
    
    @field_validator('event_date')
    @classmethod
    def event_date_must_be_future(cls, v):
        """Validate that event date is in the future."""
        if v <= datetime.now():
            raise ValueError('Event date must be in the future')
        return v


class EventCreate(EventBase):
    """Schema for creating a new event."""
    pass


class EventUpdate(BaseModel):
    """Schema for updating an existing event."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    venue: Optional[str] = Field(None, min_length=1, max_length=255)
    event_date: Optional[datetime] = None
    total_capacity: Optional[int] = Field(None, gt=0)
    price: Optional[Decimal] = Field(None, ge=0)
    has_seat_selection: Optional[bool] = None
    is_active: Optional[bool] = None
    
    @field_validator('event_date')
    @classmethod
    def event_date_must_be_future(cls, v):
        """Validate that event date is in the future."""
        if v is not None and v <= datetime.now():
            raise ValueError('Event date must be in the future')
        return v


class EventResponse(EventBase):
    """Schema for event response."""
    
    id: UUID
    available_capacity: int
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime
    is_sold_out: bool
    capacity_utilization: float
    
    model_config = ConfigDict(from_attributes=True)


class EventListResponse(BaseModel):
    """Schema for paginated event list response."""
    
    events: list[EventResponse]
    total: int
    page: int
    size: int
    pages: int


class EventFilters(BaseModel):
    """Schema for event filtering parameters."""
    
    search: Optional[str] = Field(None, description="Search in event name, description, or venue")
    venue: Optional[str] = Field(None, description="Filter by venue")
    date_from: Optional[datetime] = Field(None, description="Filter events from this date")
    date_to: Optional[datetime] = Field(None, description="Filter events until this date")
    min_price: Optional[Decimal] = Field(None, ge=0, description="Minimum ticket price")
    max_price: Optional[Decimal] = Field(None, ge=0, description="Maximum ticket price")
    available_only: bool = Field(default=True, description="Show only events with available capacity")
    active_only: bool = Field(default=True, description="Show only active events")
    
    @field_validator('max_price')
    @classmethod
    def max_price_greater_than_min(cls, v, info):
        """Validate that max_price is greater than min_price."""
        if v is not None and info.data.get('min_price') is not None:
            if v < info.data['min_price']:
                raise ValueError('max_price must be greater than or equal to min_price')
        return v
    
    @field_validator('date_to')
    @classmethod
    def date_to_after_date_from(cls, v, info):
        """Validate that date_to is after date_from."""
        if v is not None and info.data.get('date_from') is not None:
            if v < info.data['date_from']:
                raise ValueError('date_to must be after date_from')
        return v