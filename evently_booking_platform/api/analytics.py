"""
Analytics API endpoints for admin reporting and metrics.
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from evently_booking_platform.database import get_db
from evently_booking_platform.models import User
from evently_booking_platform.schemas.analytics import (
    AnalyticsDashboard, BookingMetrics, CapacityUtilization,
    CancellationAnalytics, DailyBookingStats, EventPerformanceMetrics,
    PopularEvent, RevenueAnalytics
)
from evently_booking_platform.services.analytics_service import AnalyticsService
from evently_booking_platform.utils.dependencies import get_current_admin_user

router = APIRouter(prefix="/admin/analytics", tags=["admin", "analytics"])


@router.get("/dashboard", response_model=AnalyticsDashboard)
async def get_analytics_dashboard(
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive analytics dashboard data.
    
    Requires admin privileges.
    """
    analytics_service = AnalyticsService(db)
    return await analytics_service.get_analytics_dashboard(start_date, end_date)


@router.get("/bookings", response_model=BookingMetrics)
async def get_booking_metrics(
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get overall booking metrics including total bookings, status breakdown, and revenue.
    
    Requires admin privileges.
    """
    analytics_service = AnalyticsService(db)
    return await analytics_service.get_booking_metrics(start_date, end_date)


@router.get("/capacity", response_model=List[CapacityUtilization])
async def get_capacity_utilization(
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get capacity utilization metrics for all events.
    
    Requires admin privileges.
    """
    analytics_service = AnalyticsService(db)
    return await analytics_service.get_capacity_utilization(start_date, end_date)


@router.get("/popular-events", response_model=List[PopularEvent])
async def get_popular_events(
    limit: int = Query(10, ge=1, le=50, description="Number of events to return"),
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get popular events ranking based on bookings and revenue.
    
    Requires admin privileges.
    """
    analytics_service = AnalyticsService(db)
    return await analytics_service.get_popular_events(limit, start_date, end_date)


@router.get("/daily-stats", response_model=List[DailyBookingStats])
async def get_daily_booking_stats(
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    limit: int = Query(30, ge=1, le=365, description="Number of days to return"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get daily booking statistics and trends.
    
    Requires admin privileges.
    """
    analytics_service = AnalyticsService(db)
    return await analytics_service.get_daily_booking_stats(start_date, end_date, limit)


@router.get("/cancellations", response_model=CancellationAnalytics)
async def get_cancellation_analytics(
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get cancellation rate analytics and patterns.
    
    Requires admin privileges.
    """
    analytics_service = AnalyticsService(db)
    return await analytics_service.get_cancellation_analytics(start_date, end_date)


@router.get("/revenue", response_model=RevenueAnalytics)
async def get_revenue_analytics(
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get revenue analytics including total revenue, confirmed revenue, and averages.
    
    Requires admin privileges.
    """
    analytics_service = AnalyticsService(db)
    return await analytics_service.get_revenue_analytics(start_date, end_date)


@router.get("/events/{event_id}/performance", response_model=EventPerformanceMetrics)
async def get_event_performance(
    event_id: UUID,
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed performance metrics for a specific event.
    
    Requires admin privileges.
    """
    analytics_service = AnalyticsService(db)
    metrics = await analytics_service.get_event_performance_metrics(event_id, start_date, end_date)
    
    if not metrics:
        raise HTTPException(status_code=404, detail="Event not found")
    
    return metrics