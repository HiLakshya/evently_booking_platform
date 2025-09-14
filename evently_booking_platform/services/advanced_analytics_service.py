"""
Advanced analytics service for booking trends, predictions, and insights.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
import statistics

from sqlalchemy import and_, func, select, case, desc, asc, text, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from evently_booking_platform.models import (
    Booking, BookingStatus, Event, User, Waitlist, Seat, SeatBooking
)
from evently_booking_platform.schemas.advanced_analytics import (
    BookingTrends, BookingTrendPoint, UserBehaviorInsights,
    EventCategoryPerformance, SeasonalTrends, PredictiveInsights,
    AdvancedAnalyticsDashboard
)
from evently_booking_platform.cache import get_cache, CacheKeyBuilder

logger = logging.getLogger(__name__)


class AdvancedAnalyticsService:
    """Service for advanced analytics and insights."""

    def __init__(self, db: AsyncSession):
        """Initialize the advanced analytics service."""
        self.db = db
        self.cache = get_cache()

    async def get_booking_trends(
        self,
        period: str = "daily",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 30
    ) -> BookingTrends:
        """Get booking trends over time with various aggregation periods."""
        if not start_date:
            start_date = date.today() - timedelta(days=limit)
        if not end_date:
            end_date = date.today()

        # Define time grouping based on period
        time_groupings = {
            "hourly": func.date_trunc('hour', Booking.created_at),
            "daily": func.date_trunc('day', Booking.created_at),
            "weekly": func.date_trunc('week', Booking.created_at),
            "monthly": func.date_trunc('month', Booking.created_at)
        }

        time_group = time_groupings.get(period, time_groupings["daily"])

        # Get booking trends data
        query = select(
            time_group.label('period_start'),
            func.count(Booking.id).label('bookings_count'),
            func.coalesce(
                func.sum(case((Booking.status == BookingStatus.CONFIRMED, Booking.total_amount))),
                Decimal('0.00')
            ).label('revenue'),
            func.count(distinct(Booking.user_id)).label('unique_users'),
            func.count(case((Booking.status == BookingStatus.CONFIRMED, 1))).label('confirmed_bookings')
        ).where(
            and_(
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
        ).group_by(
            time_group
        ).order_by(
            time_group
        )

        result = await self.db.execute(query)
        rows = result.fetchall()

        # Calculate conversion rates and create trend points
        data_points = []
        total_bookings = 0
        total_revenue = Decimal('0.00')
        conversion_rates = []

        for row in rows:
            conversion_rate = (row.confirmed_bookings / row.bookings_count * 100) if row.bookings_count > 0 else 0.0
            conversion_rates.append(conversion_rate)
            
            data_points.append(BookingTrendPoint(
                timestamp=row.period_start,
                bookings_count=row.bookings_count,
                revenue=row.revenue,
                unique_users=row.unique_users,
                conversion_rate=conversion_rate
            ))
            
            total_bookings += row.bookings_count
            total_revenue += row.revenue

        # Find peak booking time
        peak_booking_time = None
        if data_points:
            peak_point = max(data_points, key=lambda x: x.bookings_count)
            peak_booking_time = peak_point.timestamp

        # Calculate growth rate (compare with previous period)
        growth_rate = 0.0
        if len(data_points) >= 2:
            recent_bookings = sum(point.bookings_count for point in data_points[-7:])  # Last week
            previous_bookings = sum(point.bookings_count for point in data_points[-14:-7])  # Previous week
            if previous_bookings > 0:
                growth_rate = ((recent_bookings - previous_bookings) / previous_bookings) * 100

        return BookingTrends(
            period=period,
            data_points=data_points,
            total_bookings=total_bookings,
            total_revenue=total_revenue,
            average_conversion_rate=statistics.mean(conversion_rates) if conversion_rates else 0.0,
            peak_booking_time=peak_booking_time,
            growth_rate=growth_rate
        )

    async def get_user_behavior_insights(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> UserBehaviorInsights:
        """Get user behavior analytics and insights."""
        if not start_date:
            start_date = date.today() - timedelta(days=90)
        if not end_date:
            end_date = date.today()

        # Average booking lead time
        lead_time_query = select(
            func.avg(
                func.extract('epoch', Event.event_date - Booking.created_at) / 86400
            ).label('avg_lead_time_days')
        ).select_from(
            Booking
        ).join(
            Event, Booking.event_id == Event.id
        ).where(
            and_(
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date,
                Booking.status == BookingStatus.CONFIRMED
            )
        )

        lead_time_result = await self.db.execute(lead_time_query)
        avg_lead_time = lead_time_result.scalar() or 0.0

        # Most popular booking time (hour of day)
        booking_time_query = select(
            func.extract('hour', Booking.created_at).label('booking_hour'),
            func.count(Booking.id).label('booking_count')
        ).where(
            and_(
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
        ).group_by(
            func.extract('hour', Booking.created_at)
        ).order_by(
            func.count(Booking.id).desc()
        ).limit(1)

        booking_time_result = await self.db.execute(booking_time_query)
        popular_hour_row = booking_time_result.first()
        most_popular_hour = int(popular_hour_row.booking_hour) if popular_hour_row else 12

        # Repeat customer rate
        repeat_customer_query = select(
            func.count(distinct(Booking.user_id)).label('total_users'),
            func.count(distinct(case((
                func.count(Booking.id).over(partition_by=Booking.user_id) > 1,
                Booking.user_id
            )))).label('repeat_users')
        ).where(
            and_(
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
        )

        repeat_result = await self.db.execute(repeat_customer_query)
        repeat_row = repeat_result.first()
        total_users = repeat_row.total_users or 1
        repeat_users = repeat_row.repeat_users or 0
        repeat_rate = (repeat_users / total_users) * 100

        # Average events per user
        events_per_user_query = select(
            func.avg(func.count(distinct(Booking.event_id)).over(partition_by=Booking.user_id))
        ).where(
            and_(
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date,
                Booking.status == BookingStatus.CONFIRMED
            )
        )

        events_per_user_result = await self.db.execute(events_per_user_query)
        avg_events_per_user = events_per_user_result.scalar() or 1.0

        # User retention rate (users who booked in both first and second half of period)
        mid_date = start_date + (end_date - start_date) / 2
        
        retention_query = select(
            func.count(distinct(case((
                func.date(Booking.created_at) < mid_date,
                Booking.user_id
            )))).label('first_half_users'),
            func.count(distinct(case((
                and_(
                    func.date(Booking.created_at) >= mid_date,
                    Booking.user_id.in_(
                        select(distinct(Booking.user_id)).where(
                            func.date(Booking.created_at) < mid_date
                        )
                    )
                ),
                Booking.user_id
            )))).label('retained_users')
        ).where(
            and_(
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date
            )
        )

        retention_result = await self.db.execute(retention_query)
        retention_row = retention_result.first()
        first_half_users = retention_row.first_half_users or 1
        retained_users = retention_row.retained_users or 0
        retention_rate = (retained_users / first_half_users) * 100

        return UserBehaviorInsights(
            average_booking_lead_time_days=float(avg_lead_time),
            most_popular_booking_time_hour=most_popular_hour,
            repeat_customer_rate=repeat_rate,
            average_events_per_user=float(avg_events_per_user),
            user_retention_rate=retention_rate,
            geographic_distribution={}  # Would need user location data
        )

    async def get_predictive_insights(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> PredictiveInsights:
        """Get predictive analytics insights."""
        if not start_date:
            start_date = date.today() - timedelta(days=90)
        if not end_date:
            end_date = date.today()

        # Calculate historical monthly averages for prediction
        monthly_avg_query = select(
            func.avg(func.count(Booking.id).over(
                partition_by=func.date_trunc('month', Booking.created_at)
            )).label('avg_monthly_bookings'),
            func.avg(func.sum(Booking.total_amount).over(
                partition_by=func.date_trunc('month', Booking.created_at)
            )).label('avg_monthly_revenue')
        ).where(
            and_(
                func.date(Booking.created_at) >= start_date,
                func.date(Booking.created_at) <= end_date,
                Booking.status == BookingStatus.CONFIRMED
            )
        )

        monthly_result = await self.db.execute(monthly_avg_query)
        monthly_row = monthly_result.first()
        
        # Apply growth trend for prediction (simplified linear prediction)
        predicted_bookings = int((monthly_row.avg_monthly_bookings or 0) * 1.1)  # 10% growth assumption
        predicted_revenue = Decimal(str((monthly_row.avg_monthly_revenue or 0) * 1.1))

        # Find trending events (high booking velocity in recent days)
        trending_query = select(
            Event.id
        ).select_from(
            Event
        ).join(
            Booking, Event.id == Booking.event_id
        ).where(
            and_(
                func.date(Booking.created_at) >= date.today() - timedelta(days=7),
                Event.event_date > datetime.utcnow(),
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.PENDING])
            )
        ).group_by(
            Event.id
        ).having(
            func.count(Booking.id) > 5  # At least 5 bookings in last week
        ).order_by(
            func.count(Booking.id).desc()
        ).limit(10)

        trending_result = await self.db.execute(trending_query)
        trending_events = [row.id for row in trending_result.fetchall()]

        # Find at-risk events (low booking velocity)
        at_risk_query = select(
            Event.id
        ).select_from(
            Event
        ).outerjoin(
            Booking, and_(
                Event.id == Booking.event_id,
                func.date(Booking.created_at) >= date.today() - timedelta(days=14)
            )
        ).where(
            and_(
                Event.event_date > datetime.utcnow(),
                Event.event_date <= datetime.utcnow() + timedelta(days=30),  # Events in next 30 days
                Event.available_capacity > Event.total_capacity * 0.7  # More than 70% capacity available
            )
        ).group_by(
            Event.id
        ).having(
            func.count(Booking.id) < 3  # Less than 3 bookings in last 2 weeks
        ).limit(10)

        at_risk_result = await self.db.execute(at_risk_query)
        at_risk_events = [row.id for row in at_risk_result.fetchall()]

        return PredictiveInsights(
            predicted_next_month_bookings=predicted_bookings,
            predicted_next_month_revenue=predicted_revenue,
            trending_events=trending_events,
            at_risk_events=at_risk_events,
            recommended_pricing_adjustments={}  # Would be populated by dynamic pricing service
        )

    async def get_advanced_analytics_dashboard(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> AdvancedAnalyticsDashboard:
        """Get comprehensive advanced analytics dashboard."""
        # Get all analytics data
        booking_trends = await self.get_booking_trends("daily", start_date, end_date)
        user_behavior = await self.get_user_behavior_insights(start_date, end_date)
        predictive_insights = await self.get_predictive_insights(start_date, end_date)

        # Simplified category performance and seasonal trends for now
        category_performance = []  # Would need event categories in the model
        seasonal_trends = []  # Would need more historical data

        return AdvancedAnalyticsDashboard(
            booking_trends=booking_trends,
            user_behavior=user_behavior,
            category_performance=category_performance,
            seasonal_trends=seasonal_trends,
            predictive_insights=predictive_insights
        )