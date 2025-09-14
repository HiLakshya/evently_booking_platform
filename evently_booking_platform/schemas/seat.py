"""
Pydantic schemas for seat management.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class SeatBase(BaseModel):
    """Base seat schema with common fields."""
    section: str = Field(..., min_length=1, max_length=50, description="Seat section")
    row: str = Field(..., min_length=1, max_length=10, description="Seat row")
    number: str = Field(..., min_length=1, max_length=10, description="Seat number")
    price: Decimal = Field(..., ge=0, description="Seat price")


class SeatCreate(SeatBase):
    """Schema for creating a new seat."""
    pass


class SeatUpdate(BaseModel):
    """Schema for updating a seat."""
    section: Optional[str] = Field(None, min_length=1, max_length=50)
    row: Optional[str] = Field(None, min_length=1, max_length=10)
    number: Optional[str] = Field(None, min_length=1, max_length=10)
    price: Optional[Decimal] = Field(None, ge=0)


class SeatResponse(SeatBase):
    """Schema for seat response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    event_id: UUID
    status: str
    is_available: bool
    seat_identifier: str
    created_at: datetime
    updated_at: datetime


class SeatMapResponse(BaseModel):
    """Schema for seat map response."""
    event_id: str
    seat_map: Dict[str, Dict[str, List[Dict[str, Any]]]]  # section -> row -> seats
    total_seats: int
    available_seats: int
    held_seats: int
    booked_seats: int


class SeatAvailabilityResponse(BaseModel):
    """Schema for seat availability check response."""
    available_seats: List[Dict[str, Any]]
    unavailable_seats: List[Dict[str, Any]]
    missing_seat_ids: List[str]
    all_available: bool


class SeatHoldRequest(BaseModel):
    """Schema for seat hold request."""
    seat_ids: List[UUID] = Field(..., min_length=1, description="List of seat IDs to hold")
    hold_duration_minutes: Optional[int] = Field(
        None, 
        ge=1, 
        le=60, 
        description="Hold duration in minutes (1-60)"
    )


class SeatHoldResponse(BaseModel):
    """Schema for seat hold response."""
    held_seat_ids: List[str]
    expires_at: datetime
    hold_duration_minutes: int


class SeatBookingRequest(BaseModel):
    """Schema for seat booking request."""
    seat_ids: List[UUID] = Field(..., min_length=1, description="List of seat IDs to book")


class SeatPricingTierResponse(BaseModel):
    """Schema for seat pricing tier response."""
    event_id: str
    pricing_tiers: Dict[str, Dict[str, Any]]


class SeatPricingUpdateRequest(BaseModel):
    """Schema for updating seat pricing."""
    section: str = Field(..., min_length=1, max_length=50)
    new_price: Decimal = Field(..., ge=0)


class BulkSeatCreateRequest(BaseModel):
    """Schema for bulk seat creation."""
    seats: List[SeatCreate] = Field(..., min_length=1, description="List of seats to create")


class SeatLayoutTemplate(BaseModel):
    """Schema for seat layout template."""
    sections: List[Dict[str, Any]] = Field(
        ..., 
        description="List of sections with their configuration"
    )
    
    class SectionConfig(BaseModel):
        """Configuration for a venue section."""
        name: str
        rows: List[str]  # e.g., ["A", "B", "C"] or ["1", "2", "3"]
        seats_per_row: int
        price: Decimal
        seat_number_start: int = 1


class GenerateSeatLayoutRequest(BaseModel):
    """Schema for generating seat layout from template."""
    template: SeatLayoutTemplate
    event_id: UUID


class SeatStatistics(BaseModel):
    """Schema for seat statistics."""
    event_id: str
    total_seats: int
    available_seats: int
    held_seats: int
    booked_seats: int
    blocked_seats: int
    capacity_utilization: float
    revenue_potential: Decimal
    current_revenue: Decimal


class SeatSelectionResponse(BaseModel):
    """Schema for seat selection response."""
    selected_seats: List[SeatResponse]
    total_price: Decimal
    hold_expires_at: Optional[datetime] = None
    recommendations: Optional[List[SeatResponse]] = None