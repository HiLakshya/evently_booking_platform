"""
Advanced analytics schemas for booking trends and insights.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


class BookingTrendPoint(BaseModel):
    """Single point in booking trend data."""
    timestamp: datetime
    bookings_count: int
    revenue: Decimal
    unique_users: int
    conversion_rate: float = Field(..., description="Percentage of users who completed booking")


class BookingTrends(BaseModel):
    """Booking trends over time."""
    period: str = Field(..., description="Time period (hourly, daily, weekly, monthly)")
    data_points: List[BookingTrendPoint]
    total_bookings: int
    total_revenue: Decimal
    average_conversion_rate: float
    peak_booking_time: Optional[datetime] = None
    growth_rate: float = Field(..., description="Percentage growth compared to previous period")


class UserBehaviorInsights(BaseModel):
    """User behavior analytics."""
    average_booking_lead_time_days: float
    most_popular_booking_time_hour: int
    repeat_customer_rate: float
    average_events_per_user: float
    user_retention_rate: float
    geographic_distribution: Dict[str, int] = Field(default_factory=dict)


class EventCategoryPerformance(BaseModel):
    """Performance metrics by event category."""
    category: str
    total_events: int
    total_bookings: int
    total_revenue: Decimal
    average_capacity_utilization: float
    average_ticket_price: Decimal
    cancellation_rate: float


class SeasonalTrends(BaseModel):
    """Seasonal booking trends."""
    season: str
    booking_volume_change: float = Field(..., description="Percentage change from baseline")
    revenue_change: float
    popular_event_types: List[str]
    peak_months: List[str]


class PredictiveInsights(BaseModel):
    """Predictive analytics insights."""
    predicted_next_month_bookings: int
    predicted_next_month_revenue: Decimal
    trending_events: List[UUID]
    at_risk_events: List[UUID] = Field(..., description="Events with low booking velocity")
    recommended_pricing_adjustments: Dict[UUID, float] = Field(default_factory=dict)


class AdvancedAnalyticsDashboard(BaseModel):
    """Comprehensive advanced analytics dashboard."""
    booking_trends: BookingTrends
    user_behavior: UserBehaviorInsights
    category_performance: List[EventCategoryPerformance]
    seasonal_trends: List[SeasonalTrends]
    predictive_insights: PredictiveInsights
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class SeatRecommendation(BaseModel):
    """Seat recommendation for a user."""
    seat_id: UUID
    section: str
    row: str
    number: str
    price: Decimal
    score: float = Field(..., description="Recommendation score (0-1)")
    reasons: List[str] = Field(..., description="Reasons for recommendation")


class SeatRecommendationRequest(BaseModel):
    """Request for seat recommendations."""
    event_id: UUID
    user_id: UUID
    quantity: int = Field(ge=1, le=10)
    max_price: Optional[Decimal] = None
    preferred_sections: Optional[List[str]] = None
    accessibility_required: bool = False


class SeatRecommendationResponse(BaseModel):
    """Response with seat recommendations."""
    event_id: UUID
    recommendations: List[List[SeatRecommendation]] = Field(
        ..., description="Groups of seats that can be booked together"
    )
    total_options: int
    algorithm_used: str


class BulkBookingRequest(BaseModel):
    """Request for bulk booking operation."""
    event_id: UUID
    user_id: UUID
    quantity: int = Field(ge=2, le=100)
    seat_ids: Optional[List[UUID]] = None
    group_name: Optional[str] = None
    special_requirements: Optional[str] = None
    discount_code: Optional[str] = None


class BulkBookingResponse(BaseModel):
    """Response for bulk booking operation."""
    booking_id: UUID
    event_id: UUID
    total_quantity: int
    total_amount: Decimal
    discount_applied: Optional[Decimal] = None
    group_discount_percentage: Optional[float] = None
    seat_assignments: List[Dict[str, Any]]
    confirmation_code: str


class EventRecommendation(BaseModel):
    """Event recommendation for a user."""
    event_id: UUID
    event_name: str
    venue: str
    event_date: datetime
    price: Decimal
    score: float = Field(..., description="Recommendation score (0-1)")
    reasons: List[str] = Field(..., description="Reasons for recommendation")
    similarity_to_past_bookings: float
    popularity_score: float
    availability_score: float


class EventRecommendationRequest(BaseModel):
    """Request for event recommendations."""
    user_id: UUID
    limit: int = Field(default=10, ge=1, le=50)
    include_categories: Optional[List[str]] = None
    exclude_categories: Optional[List[str]] = None
    max_price: Optional[Decimal] = None
    date_range_start: Optional[date] = None
    date_range_end: Optional[date] = None


class EventRecommendationResponse(BaseModel):
    """Response with event recommendations."""
    user_id: UUID
    recommendations: List[EventRecommendation]
    algorithm_used: str
    personalization_score: float = Field(..., description="How personalized the recommendations are")


class DynamicPricingRule(BaseModel):
    """Dynamic pricing rule configuration."""
    event_id: UUID
    base_price: Decimal
    demand_multiplier: float = Field(default=1.0, ge=0.5, le=3.0)
    time_multiplier: float = Field(default=1.0, ge=0.8, le=2.0)
    capacity_threshold_high: float = Field(default=0.8, ge=0.5, le=1.0)
    capacity_threshold_low: float = Field(default=0.3, ge=0.0, le=0.5)
    max_price_increase: float = Field(default=0.5, ge=0.0, le=1.0)
    max_price_decrease: float = Field(default=0.2, ge=0.0, le=0.5)


class DynamicPricingUpdate(BaseModel):
    """Dynamic pricing update result."""
    event_id: UUID
    old_price: Decimal
    new_price: Decimal
    price_change_percentage: float
    reason: str
    effective_immediately: bool = True


class SystemHealthMetrics(BaseModel):
    """Comprehensive system health metrics."""
    database_health: Dict[str, Any]
    cache_health: Dict[str, Any]
    api_performance: Dict[str, Any]
    booking_system_health: Dict[str, Any]
    external_services_health: Dict[str, Any]
    resource_usage: Dict[str, Any]
    error_rates: Dict[str, float]
    response_times: Dict[str, float]
    active_connections: int
    queue_sizes: Dict[str, int]
    last_updated: datetime = Field(default_factory=datetime.utcnow)