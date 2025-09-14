"""
Pydantic schemas for analytics and reporting.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class BookingMetrics(BaseModel):
    """Schema for booking metrics."""
    total_bookings: int = Field(..., description="Total number of bookings")
    confirmed_bookings: int = Field(..., description="Number of confirmed bookings")
    cancelled_bookings: int = Field(..., description="Number of cancelled bookings")
    pending_bookings: int = Field(..., description="Number of pending bookings")
    expired_bookings: int = Field(..., description="Number of expired bookings")
    total_revenue: Decimal = Field(..., description="Total revenue from bookings")
    average_booking_value: Decimal = Field(..., description="Average booking value")


class CapacityUtilization(BaseModel):
    """Schema for capacity utilization metrics."""
    event_id: UUID = Field(..., description="Event ID")
    event_name: str = Field(..., description="Event name")
    total_capacity: int = Field(..., description="Total event capacity")
    booked_capacity: int = Field(..., description="Number of booked seats")
    available_capacity: int = Field(..., description="Number of available seats")
    utilization_percentage: float = Field(..., description="Capacity utilization percentage")


class PopularEvent(BaseModel):
    """Schema for popular events ranking."""
    event_id: UUID = Field(..., description="Event ID")
    event_name: str = Field(..., description="Event name")
    venue: str = Field(..., description="Event venue")
    event_date: datetime = Field(..., description="Event date")
    total_bookings: int = Field(..., description="Total number of bookings")
    total_tickets_sold: int = Field(..., description="Total tickets sold")
    revenue: Decimal = Field(..., description="Total revenue")
    capacity_utilization: float = Field(..., description="Capacity utilization percentage")


class DailyBookingStats(BaseModel):
    """Schema for daily booking statistics."""
    booking_date: date = Field(..., description="Date of the statistics")
    total_bookings: int = Field(..., description="Total bookings for the day")
    confirmed_bookings: int = Field(..., description="Confirmed bookings for the day")
    cancelled_bookings: int = Field(..., description="Cancelled bookings for the day")
    revenue: Decimal = Field(..., description="Revenue for the day")
    unique_users: int = Field(..., description="Number of unique users who made bookings")
    
    class Config:
        populate_by_name = True


class CancellationAnalytics(BaseModel):
    """Schema for cancellation rate analytics."""
    total_bookings: int = Field(..., description="Total number of bookings")
    cancelled_bookings: int = Field(..., description="Number of cancelled bookings")
    cancellation_rate: float = Field(..., description="Cancellation rate as percentage")
    average_time_to_cancellation_hours: Optional[float] = Field(
        None, description="Average time from booking to cancellation in hours"
    )


class RevenueAnalytics(BaseModel):
    """Schema for revenue analytics."""
    total_revenue: Decimal = Field(..., description="Total revenue")
    confirmed_revenue: Decimal = Field(..., description="Revenue from confirmed bookings")
    pending_revenue: Decimal = Field(..., description="Revenue from pending bookings")
    average_revenue_per_booking: Decimal = Field(..., description="Average revenue per booking")
    average_revenue_per_user: Decimal = Field(..., description="Average revenue per user")


class EventPerformanceMetrics(BaseModel):
    """Schema for event performance metrics."""
    event_id: UUID = Field(..., description="Event ID")
    event_name: str = Field(..., description="Event name")
    venue: str = Field(..., description="Event venue")
    event_date: datetime = Field(..., description="Event date")
    total_capacity: int = Field(..., description="Total event capacity")
    tickets_sold: int = Field(..., description="Number of tickets sold")
    revenue: Decimal = Field(..., description="Total revenue")
    capacity_utilization: float = Field(..., description="Capacity utilization percentage")
    booking_velocity: float = Field(..., description="Bookings per day since event creation")
    cancellation_rate: float = Field(..., description="Cancellation rate for this event")
    waitlist_size: int = Field(..., description="Current waitlist size")


class AnalyticsDashboard(BaseModel):
    """Schema for comprehensive analytics dashboard."""
    booking_metrics: BookingMetrics = Field(..., description="Overall booking metrics")
    revenue_analytics: RevenueAnalytics = Field(..., description="Revenue analytics")
    cancellation_analytics: CancellationAnalytics = Field(..., description="Cancellation analytics")
    popular_events: List[PopularEvent] = Field(..., description="Top 10 popular events")
    capacity_utilization: List[CapacityUtilization] = Field(..., description="Capacity utilization by event")
    daily_stats: List[DailyBookingStats] = Field(..., description="Daily booking statistics")


class AnalyticsFilters(BaseModel):
    """Schema for analytics filters."""
    start_date: Optional[date] = Field(None, description="Start date for filtering")
    end_date: Optional[date] = Field(None, description="End date for filtering")
    event_id: Optional[UUID] = Field(None, description="Filter by specific event")
    limit: int = Field(10, ge=1, le=100, description="Limit for results")