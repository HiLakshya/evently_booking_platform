"""
Advanced analytics API endpoints for booking trends and insights.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from evently_booking_platform.database import get_db
from evently_booking_platform.models import User
from evently_booking_platform.schemas.advanced_analytics import (
    BookingTrends, UserBehaviorInsights, PredictiveInsights,
    AdvancedAnalyticsDashboard, SeatRecommendationRequest,
    SeatRecommendationResponse, BulkBookingRequest, BulkBookingResponse,
    EventRecommendationRequest, EventRecommendationResponse,
    DynamicPricingRule, DynamicPricingUpdate, SystemHealthMetrics
)
from evently_booking_platform.services.advanced_analytics_service import AdvancedAnalyticsService
from evently_booking_platform.services.seat_recommendation_service import SeatRecommendationService
from evently_booking_platform.services.bulk_booking_service import BulkBookingService
from evently_booking_platform.services.event_recommendation_service import EventRecommendationService
from evently_booking_platform.services.dynamic_pricing_service import DynamicPricingService
from evently_booking_platform.utils.dependencies import get_current_admin_user, get_current_user
from evently_booking_platform.services.enhanced_health_service import HealthCheckService

router = APIRouter(prefix="/advanced", tags=["advanced"])


# Advanced Analytics Endpoints
@router.get("/analytics/trends", response_model=BookingTrends)
async def get_booking_trends(
    period: str = Query("daily", regex="^(hourly|daily|weekly|monthly)$"),
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    limit: int = Query(30, ge=1, le=365, description="Number of periods to return"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get booking trends over time with various aggregation periods.
    
    Requires admin privileges.
    """
    analytics_service = AdvancedAnalyticsService(db)
    return await analytics_service.get_booking_trends(period, start_date, end_date, limit)


@router.get("/analytics/user-behavior", response_model=UserBehaviorInsights)
async def get_user_behavior_insights(
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user behavior analytics and insights.
    
    Requires admin privileges.
    """
    analytics_service = AdvancedAnalyticsService(db)
    return await analytics_service.get_user_behavior_insights(start_date, end_date)


@router.get("/analytics/predictions", response_model=PredictiveInsights)
async def get_predictive_insights(
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get predictive analytics insights.
    
    Requires admin privileges.
    """
    analytics_service = AdvancedAnalyticsService(db)
    return await analytics_service.get_predictive_insights(start_date, end_date)


@router.get("/analytics/dashboard", response_model=AdvancedAnalyticsDashboard)
async def get_advanced_analytics_dashboard(
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive advanced analytics dashboard.
    
    Requires admin privileges.
    """
    analytics_service = AdvancedAnalyticsService(db)
    return await analytics_service.get_advanced_analytics_dashboard(start_date, end_date)


# Seat Recommendation Endpoints
@router.post("/seats/recommendations", response_model=SeatRecommendationResponse)
async def get_seat_recommendations(
    request: SeatRecommendationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get intelligent seat recommendations based on user preferences and algorithms.
    """
    # Ensure user can only get recommendations for themselves unless admin
    if request.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Can only get recommendations for yourself")
    
    recommendation_service = SeatRecommendationService(db)
    return await recommendation_service.get_seat_recommendations(request)


# Bulk Booking Endpoints
@router.post("/bookings/bulk", response_model=BulkBookingResponse)
async def create_bulk_booking(
    request: BulkBookingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a bulk booking for group purchases.
    """
    # Ensure user can only create bookings for themselves unless admin
    if request.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Can only create bookings for yourself")
    
    bulk_booking_service = BulkBookingService(db)
    return await bulk_booking_service.create_bulk_booking(request)


# Event Recommendation Endpoints
@router.post("/events/recommendations", response_model=EventRecommendationResponse)
async def get_event_recommendations(
    request: EventRecommendationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get personalized event recommendations based on user history and preferences.
    """
    # Ensure user can only get recommendations for themselves unless admin
    if request.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Can only get recommendations for yourself")
    
    recommendation_service = EventRecommendationService(db)
    return await recommendation_service.get_event_recommendations(request)


# Dynamic Pricing Endpoints
@router.post("/pricing/update/{event_id}", response_model=DynamicPricingUpdate)
async def update_event_pricing(
    event_id: UUID,
    pricing_rule: Optional[DynamicPricingRule] = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update dynamic pricing for a specific event.
    
    Requires admin privileges.
    """
    pricing_service = DynamicPricingService(db)
    return await pricing_service.update_event_pricing(event_id, pricing_rule)


@router.post("/pricing/update-all", response_model=list[DynamicPricingUpdate])
async def update_all_event_pricing(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update dynamic pricing for all active events.
    
    Requires admin privileges.
    """
    pricing_service = DynamicPricingService(db)
    return await pricing_service.update_all_event_pricing()


# Enhanced Health Check Endpoints
@router.get("/health/comprehensive", response_model=SystemHealthMetrics)
async def get_comprehensive_health_status():
    """
    Get comprehensive system health metrics including all components.
    """
    health_service = HealthCheckService()
    return await health_service.get_comprehensive_health_status()


@router.get("/health/monitoring")
async def get_monitoring_metrics():
    """
    Get detailed monitoring metrics for system observability.
    """
    health_service = HealthCheckService()
    health_status = await health_service.get_comprehensive_health_status()
    
    return {
        "system_health": health_status,
        "alerts": await _get_system_alerts(health_status),
        "recommendations": await _get_system_recommendations(health_status)
    }


async def _get_system_alerts(health_status: SystemHealthMetrics) -> list:
    """Generate system alerts based on health status."""
    alerts = []
    
    # Database alerts
    if health_status.database_health.get("status") != "healthy":
        alerts.append({
            "severity": "critical",
            "component": "database",
            "message": "Database health check failed",
            "details": health_status.database_health
        })
    
    # Cache alerts
    if health_status.cache_health.get("status") != "healthy":
        alerts.append({
            "severity": "warning",
            "component": "cache",
            "message": "Cache health check failed",
            "details": health_status.cache_health
        })
    
    # Resource usage alerts
    cpu_usage = health_status.resource_usage.get("cpu_usage_percent", 0)
    if cpu_usage > 80:
        alerts.append({
            "severity": "warning",
            "component": "system",
            "message": f"High CPU usage: {cpu_usage}%",
            "details": {"cpu_usage": cpu_usage}
        })
    
    memory_usage = health_status.resource_usage.get("memory_usage_percent", 0)
    if memory_usage > 85:
        alerts.append({
            "severity": "critical",
            "component": "system",
            "message": f"High memory usage: {memory_usage}%",
            "details": {"memory_usage": memory_usage}
        })
    
    return alerts


async def _get_system_recommendations(health_status: SystemHealthMetrics) -> list:
    """Generate system recommendations based on health status."""
    recommendations = []
    
    # Performance recommendations
    db_response_time = health_status.database_health.get("complex_query_time_ms", 0)
    if db_response_time > 100:
        recommendations.append({
            "category": "performance",
            "priority": "medium",
            "message": "Database query performance is slow",
            "suggestion": "Consider optimizing database queries or adding indexes"
        })
    
    cache_hit_rate = health_status.cache_health.get("hit_rate_percentage", 100)
    if cache_hit_rate < 80:
        recommendations.append({
            "category": "performance",
            "priority": "medium",
            "message": f"Cache hit rate is low: {cache_hit_rate}%",
            "suggestion": "Review caching strategy and TTL settings"
        })
    
    # Capacity recommendations
    disk_usage = health_status.resource_usage.get("disk_usage_percent", 0)
    if disk_usage > 70:
        recommendations.append({
            "category": "capacity",
            "priority": "high",
            "message": f"Disk usage is high: {disk_usage}%",
            "suggestion": "Consider cleaning up logs or expanding disk capacity"
        })
    
    return recommendations