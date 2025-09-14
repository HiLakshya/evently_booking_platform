"""
Analytics service for booking metrics and reporting.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from evently_booking_platform.models import (
    Booking, Event, User, Waitlist
)
from evently_booking_platform.schemas.analytics import (
    AnalyticsDashboard, BookingMetrics, CapacityUtilization,
    CancellationAnalytics, DailyBookingStats, EventPerformanceMetrics,
    PopularEvent, RevenueAnalytics
)


class AnalyticsService:
    """Service for analytics and reporting operations."""

    def __init__(self, db: AsyncSession):
        """Initialize the analytics service."""
        self.db = db

    async def get_booking_metrics(
        self, 
        start_date: Optional[date] = None, 
        end_date: Optional[date] = None
    ) -> BookingMetrics:
        """Get overall booking metrics."""
        query = select(
            func.count(Booking.id).label('total_bookings'),
            func.count(case((Booking.status == 'CONFIRMED', 1))).label('confirmed_bookings'),
            func.count(case((Booking.status == 'CANCELLED', 1))).label('cancelled_bookings'),
            func.count(case((Booking.status == 'PENDING', 1))).label('pending_bookings'),
            func.coalesce(
                func.sum(case((Booking.status == 'CONFIRMED', Booking.total_amount))), 
                Decimal('0.00')
            ).label('total_revenue'),
            func.coalesce(
                func.avg(case((Booking.status == 'CONFIRMED', Booking.total_amount))), 
                Decimal('0.00')
            ).label('average_booking_value')
        )

        if start_date:
            query = query.where(Booking.created_at >= start_date)
        if end_date:
            query = query.where(Booking.created_at <= end_date)

        result = await self.db.execute(query)
        row = result.first()

        return BookingMetrics(
            total_bookings=row.total_bookings or 0,
            confirmed_bookings=row.confirmed_bookings or 0,
            cancelled_bookings=row.cancelled_bookings or 0,
            pending_bookings=row.pending_bookings or 0,
            expired_bookings=0,  # Not supported in current database schema
            total_revenue=row.total_revenue or Decimal('0.00'),
            average_booking_value=row.average_booking_value or Decimal('0.00')
        )

    async def get_capacity_utilization(
        self, 
        start_date: Optional[date] = None, 
        end_date: Optional[date] = None
    ) -> List[CapacityUtilization]:
        """Get capacity utilization metrics for events."""
        query = select(
            Event.id,
            Event.name,
            Event.total_capacity,
            Event.available_capacity
        ).where(Event.is_active == True)

        if start_date:
            query = query.where(Event.event_date >= start_date)
        if end_date:
            query = query.where(Event.event_date <= end_date)

        query = query.order_by(Event.event_date)

        result = await self.db.execute(query)
        rows = result.fetchall()

        return [
            CapacityUtilization(
                event_id=row.id,
                event_name=row.name,
                total_capacity=row.total_capacity,
                booked_capacity=row.total_capacity - row.available_capacity,
                available_capacity=row.available_capacity,
                utilization_percentage=((row.total_capacity - row.available_capacity) / row.total_capacity * 100) if row.total_capacity > 0 else 0.0
            )
            for row in rows
        ]

    async def get_popular_events(
        self, 
        limit: int = 10,
        start_date: Optional[date] = None, 
        end_date: Optional[date] = None
    ) -> List[PopularEvent]:
        """Get popular events ranking based on bookings and revenue."""
        query = select(
            Event.id,
            Event.name,
            Event.venue,
            Event.event_date,
            Event.total_capacity,
            Event.available_capacity,
            func.count(Booking.id).label('total_bookings'),
            func.coalesce(func.sum(Booking.quantity), 0).label('total_tickets_sold'),
            func.coalesce(
                func.sum(case((Booking.status == 'CONFIRMED', Booking.total_amount))), 
                Decimal('0.00')
            ).label('revenue'),
            Event.total_capacity,
            Event.available_capacity
        ).select_from(
            Event
        ).outerjoin(
            Booking, and_(
                Event.id == Booking.event_id,
                Booking.status.in_(['CONFIRMED', 'PENDING'])
            )
        ).where(Event.is_active == True)

        if start_date:
            query = query.where(Event.event_date >= start_date)
        if end_date:
            query = query.where(Event.event_date <= end_date)

        query = query.group_by(
            Event.id, Event.name, Event.venue, Event.event_date, 
            Event.total_capacity, Event.available_capacity
        ).order_by(
            func.count(Booking.id).desc(),
            func.coalesce(
                func.sum(case((Booking.status == 'CONFIRMED', Booking.total_amount))), 
                Decimal('0.00')
            ).desc()
        ).limit(limit)

        result = await self.db.execute(query)
        rows = result.fetchall()

        return [
            PopularEvent(
                event_id=row.id,
                event_name=row.name,
                venue=row.venue,
                event_date=row.event_date,
                total_bookings=row.total_bookings or 0,
                total_tickets_sold=row.total_tickets_sold or 0,
                revenue=row.revenue or Decimal('0.00'),
                capacity_utilization=((row.total_capacity - row.available_capacity) / row.total_capacity * 100) if row.total_capacity > 0 else 0.0
            )
            for row in rows
        ]

    async def get_daily_booking_stats(
        self, 
        start_date: Optional[date] = None, 
        end_date: Optional[date] = None,
        limit: int = 30
    ) -> List[DailyBookingStats]:
        """Get daily booking statistics."""
        if not start_date:
            start_date = date.today() - timedelta(days=limit)
        if not end_date:
            end_date = date.today()

        query = select(
            func.date(Booking.created_at).label('booking_date'),
            func.count(Booking.id).label('total_bookings'),
            func.count(case((Booking.status == 'CONFIRMED', 1))).label('confirmed_bookings'),
            func.count(case((Booking.status == 'CANCELLED', 1))).label('cancelled_bookings'),
            func.coalesce(
                func.sum(case((Booking.status == 'CONFIRMED', Booking.total_amount))), 
                Decimal('0.00')
            ).label('revenue'),
            func.count(func.distinct(Booking.user_id)).label('unique_users')
        ).where(
            and_(
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
        ).group_by(
            func.date(Booking.created_at)
        ).order_by(
            func.date(Booking.created_at).desc()
        )

        result = await self.db.execute(query)
        rows = result.fetchall()

        return [
            DailyBookingStats(
                booking_date=row.booking_date,
                total_bookings=row.total_bookings or 0,
                confirmed_bookings=row.confirmed_bookings or 0,
                cancelled_bookings=row.cancelled_bookings or 0,
                revenue=row.revenue or Decimal('0.00'),
                unique_users=row.unique_users or 0
            )
            for row in rows
        ]

    async def get_cancellation_analytics(
        self, 
        start_date: Optional[date] = None, 
        end_date: Optional[date] = None
    ) -> CancellationAnalytics:
        """Get cancellation rate analytics."""
        query = select(
            func.count(Booking.id).label('total_bookings'),
            func.count(case((Booking.status == 'CANCELLED', 1))).label('cancelled_bookings'),
            func.avg(
                case((
                    Booking.status == 'CANCELLED',
                    func.extract('epoch', Booking.updated_at - Booking.created_at) / 3600
                ))
            ).label('avg_time_to_cancellation_hours')
        )

        if start_date:
            query = query.where(Booking.created_at >= start_date)
        if end_date:
            query = query.where(Booking.created_at <= end_date)

        result = await self.db.execute(query)
        row = result.first()

        total_bookings = row.total_bookings or 0
        cancelled_bookings = row.cancelled_bookings or 0
        cancellation_rate = (cancelled_bookings / total_bookings * 100) if total_bookings > 0 else 0.0

        return CancellationAnalytics(
            total_bookings=total_bookings,
            cancelled_bookings=cancelled_bookings,
            cancellation_rate=cancellation_rate,
            average_time_to_cancellation_hours=float(row.avg_time_to_cancellation_hours or 0.0)
        )

    async def get_revenue_analytics(
        self, 
        start_date: Optional[date] = None, 
        end_date: Optional[date] = None
    ) -> RevenueAnalytics:
        """Get revenue analytics."""
        query = select(
            func.coalesce(func.sum(Booking.total_amount), Decimal('0.00')).label('total_revenue'),
            func.coalesce(
                func.sum(case((Booking.status == 'CONFIRMED', Booking.total_amount))), 
                Decimal('0.00')
            ).label('confirmed_revenue'),
            func.coalesce(
                func.sum(case((Booking.status == 'PENDING', Booking.total_amount))), 
                Decimal('0.00')
            ).label('pending_revenue'),
            func.coalesce(func.avg(Booking.total_amount), Decimal('0.00')).label('avg_revenue_per_booking'),
            func.count(func.distinct(Booking.user_id)).label('unique_users')
        )

        if start_date:
            query = query.where(Booking.created_at >= start_date)
        if end_date:
            query = query.where(Booking.created_at <= end_date)

        result = await self.db.execute(query)
        row = result.first()

        unique_users = row.unique_users or 1  # Avoid division by zero
        avg_revenue_per_user = (row.confirmed_revenue or Decimal('0.00')) / unique_users

        return RevenueAnalytics(
            total_revenue=row.total_revenue or Decimal('0.00'),
            confirmed_revenue=row.confirmed_revenue or Decimal('0.00'),
            pending_revenue=row.pending_revenue or Decimal('0.00'),
            average_revenue_per_booking=row.avg_revenue_per_booking or Decimal('0.00'),
            average_revenue_per_user=avg_revenue_per_user
        )

    async def get_event_performance_metrics(
        self, 
        event_id: UUID,
        start_date: Optional[date] = None, 
        end_date: Optional[date] = None
    ) -> Optional[EventPerformanceMetrics]:
        """Get performance metrics for a specific event."""
        # Get event details and booking metrics
        query = select(
            Event.id,
            Event.name,
            Event.venue,
            Event.event_date,
            Event.total_capacity,
            Event.available_capacity,
            Event.created_at,
            func.count(Booking.id).label('total_bookings'),
            func.coalesce(func.sum(Booking.quantity), 0).label('tickets_sold'),
            func.coalesce(
                func.sum(case((Booking.status == 'CONFIRMED', Booking.total_amount))), 
                Decimal('0.00')
            ).label('revenue'),
            func.count(case((Booking.status == 'CANCELLED', 1))).label('cancelled_bookings')
        ).select_from(
            Event
        ).outerjoin(
            Booking, Event.id == Booking.event_id
        ).where(Event.id == event_id)

        if start_date:
            query = query.where(Booking.created_at >= start_date)
        if end_date:
            query = query.where(Booking.created_at <= end_date)

        query = query.group_by(
            Event.id, Event.name, Event.venue, Event.event_date, 
            Event.total_capacity, Event.available_capacity, Event.created_at
        )

        result = await self.db.execute(query)
        row = result.first()

        if not row:
            return None

        # Get waitlist size
        waitlist_query = select(func.count(Waitlist.id)).where(Waitlist.event_id == event_id)
        waitlist_result = await self.db.execute(waitlist_query)
        waitlist_size = waitlist_result.scalar() or 0

        # Calculate metrics
        capacity_utilization = ((row.total_capacity - row.available_capacity) / row.total_capacity * 100) if row.total_capacity > 0 else 0.0
        
        days_since_creation = (datetime.utcnow() - row.created_at).days or 1
        booking_velocity = (row.total_bookings or 0) / days_since_creation

        total_bookings = row.total_bookings or 0
        cancelled_bookings = row.cancelled_bookings or 0
        cancellation_rate = (cancelled_bookings / total_bookings * 100) if total_bookings > 0 else 0.0

        return EventPerformanceMetrics(
            event_id=row.id,
            event_name=row.name,
            venue=row.venue,
            event_date=row.event_date,
            total_capacity=row.total_capacity,
            tickets_sold=row.tickets_sold or 0,
            revenue=row.revenue or Decimal('0.00'),
            capacity_utilization=capacity_utilization,
            booking_velocity=booking_velocity,
            cancellation_rate=cancellation_rate,
            waitlist_size=waitlist_size
        )

    async def get_analytics_dashboard(
        self, 
        start_date: Optional[date] = None, 
        end_date: Optional[date] = None
    ) -> AnalyticsDashboard:
        """Get comprehensive analytics dashboard data."""
        # Get all analytics data concurrently
        booking_metrics = await self.get_booking_metrics(start_date, end_date)
        revenue_analytics = await self.get_revenue_analytics(start_date, end_date)
        cancellation_analytics = await self.get_cancellation_analytics(start_date, end_date)
        popular_events = await self.get_popular_events(10, start_date, end_date)
        capacity_utilization = await self.get_capacity_utilization(start_date, end_date)
        daily_stats = await self.get_daily_booking_stats(start_date, end_date, 30)

        return AnalyticsDashboard(
            booking_metrics=booking_metrics,
            revenue_analytics=revenue_analytics,
            cancellation_analytics=cancellation_analytics,
            popular_events=popular_events,
            capacity_utilization=capacity_utilization,
            daily_stats=daily_stats
        )