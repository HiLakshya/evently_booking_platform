"""
Dynamic pricing service for demand-based price adjustments.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select, and_, func, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from evently_booking_platform.models import (
    Event, Booking, BookingStatus, Waitlist
)
from evently_booking_platform.schemas.advanced_analytics import (
    DynamicPricingRule, DynamicPricingUpdate
)
from evently_booking_platform.cache import get_cache, CacheKeyBuilder
from evently_booking_platform.utils.exceptions import EventNotFoundError

logger = logging.getLogger(__name__)


class DynamicPricingService:
    """Service for dynamic pricing based on demand and other factors."""

    def __init__(self, db: AsyncSession):
        """Initialize the dynamic pricing service."""
        self.db = db
        self.cache = get_cache()

    async def update_event_pricing(
        self,
        event_id: UUID,
        pricing_rule: Optional[DynamicPricingRule] = None
    ) -> DynamicPricingUpdate:
        """Update pricing for a specific event based on demand and rules."""
        # Get event details
        event_query = select(Event).where(Event.id == event_id)
        event_result = await self.db.execute(event_query)
        event = event_result.scalar_one_or_none()
        
        if not event:
            raise EventNotFoundError(f"Event {event_id} not found")

        # Use provided rule or create default rule
        if not pricing_rule:
            pricing_rule = DynamicPricingRule(
                event_id=event_id,
                base_price=event.price,
                demand_multiplier=1.0,
                time_multiplier=1.0,
                capacity_threshold_high=0.8,
                capacity_threshold_low=0.3,
                max_price_increase=0.5,
                max_price_decrease=0.2
            )

        # Calculate new price
        new_price = await self._calculate_dynamic_price(event, pricing_rule)
        old_price = event.price
        
        # Calculate price change percentage
        price_change_pct = float((new_price - old_price) / old_price * 100) if old_price > 0 else 0.0
        
        # Generate reason for price change
        reason = await self._generate_pricing_reason(event, pricing_rule, new_price, old_price)

        # Update event price if there's a significant change (>= 1%)
        if abs(price_change_pct) >= 1.0:
            await self.db.execute(
                update(Event)
                .where(Event.id == event_id)
                .values(
                    price=new_price,
                    updated_at=datetime.utcnow()
                )
            )
            await self.db.commit()
            
            # Invalidate cache
            cache_key = CacheKeyBuilder.event_details(event_id)
            await self.cache.delete(cache_key)

        return DynamicPricingUpdate(
            event_id=event_id,
            old_price=old_price,
            new_price=new_price,
            price_change_percentage=price_change_pct,
            reason=reason,
            effective_immediately=abs(price_change_pct) >= 1.0
        )

    async def update_all_event_pricing(self) -> List[DynamicPricingUpdate]:
        """Update pricing for all active events."""
        # Get all active events that are in the future
        events_query = select(Event).where(
            and_(
                Event.is_active == True,
                Event.event_date > datetime.utcnow()
            )
        )
        
        events_result = await self.db.execute(events_query)
        events = events_result.scalars().all()

        updates = []
        for event in events:
            try:
                update = await self.update_event_pricing(event.id)
                updates.append(update)
            except Exception as e:
                logger.error(f"Failed to update pricing for event {event.id}: {e}")
                continue

        return updates

    async def _calculate_dynamic_price(
        self,
        event: Event,
        pricing_rule: DynamicPricingRule
    ) -> Decimal:
        """Calculate the new dynamic price based on various factors."""
        base_price = pricing_rule.base_price
        
        # Factor 1: Demand-based pricing (capacity utilization)
        demand_multiplier = await self._calculate_demand_multiplier(event, pricing_rule)
        
        # Factor 2: Time-based pricing (proximity to event date)
        time_multiplier = self._calculate_time_multiplier(event, pricing_rule)
        
        # Factor 3: Booking velocity (recent booking activity)
        velocity_multiplier = await self._calculate_velocity_multiplier(event)
        
        # Factor 4: Waitlist pressure
        waitlist_multiplier = await self._calculate_waitlist_multiplier(event)

        # Combine all multipliers
        total_multiplier = (
            demand_multiplier * 0.4 +      # 40% weight on demand
            time_multiplier * 0.25 +       # 25% weight on time
            velocity_multiplier * 0.25 +   # 25% weight on velocity
            waitlist_multiplier * 0.1      # 10% weight on waitlist
        )

        # Apply multiplier to base price
        new_price = base_price * Decimal(str(total_multiplier))
        
        # Apply constraints
        max_increase = base_price * (1 + Decimal(str(pricing_rule.max_price_increase)))
        max_decrease = base_price * (1 - Decimal(str(pricing_rule.max_price_decrease)))
        
        new_price = min(max(new_price, max_decrease), max_increase)
        
        # Round to 2 decimal places
        return new_price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    async def _calculate_demand_multiplier(
        self,
        event: Event,
        pricing_rule: DynamicPricingRule
    ) -> float:
        """Calculate demand multiplier based on capacity utilization."""
        if event.total_capacity == 0:
            return 1.0

        capacity_utilization = (event.total_capacity - event.available_capacity) / event.total_capacity
        
        if capacity_utilization >= pricing_rule.capacity_threshold_high:
            # High demand - increase price
            excess_demand = capacity_utilization - pricing_rule.capacity_threshold_high
            max_excess = 1.0 - pricing_rule.capacity_threshold_high
            multiplier = 1.0 + (excess_demand / max_excess) * 0.3  # Up to 30% increase
        elif capacity_utilization <= pricing_rule.capacity_threshold_low:
            # Low demand - decrease price
            demand_deficit = pricing_rule.capacity_threshold_low - capacity_utilization
            multiplier = 1.0 - (demand_deficit / pricing_rule.capacity_threshold_low) * 0.2  # Up to 20% decrease
        else:
            # Normal demand - neutral pricing
            multiplier = 1.0

        return multiplier

    def _calculate_time_multiplier(
        self,
        event: Event,
        pricing_rule: DynamicPricingRule
    ) -> float:
        """Calculate time multiplier based on proximity to event date."""
        days_until_event = (event.event_date - datetime.utcnow()).days
        
        if days_until_event <= 1:
            # Last minute - premium pricing
            return 1.2
        elif days_until_event <= 7:
            # One week - moderate increase
            return 1.1
        elif days_until_event <= 30:
            # One month - normal pricing
            return 1.0
        elif days_until_event <= 90:
            # Early bird - slight discount
            return 0.95
        else:
            # Very early - early bird discount
            return 0.9

    async def _calculate_velocity_multiplier(self, event: Event) -> float:
        """Calculate velocity multiplier based on recent booking activity."""
        # Get booking count in the last 7 days
        recent_bookings_query = select(
            func.count(Booking.id)
        ).where(
            and_(
                Booking.event_id == event.id,
                Booking.created_at >= datetime.utcnow() - timedelta(days=7),
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.PENDING])
            )
        )
        
        recent_bookings_result = await self.db.execute(recent_bookings_query)
        recent_bookings = recent_bookings_result.scalar() or 0

        # Get booking count in the previous 7 days for comparison
        previous_bookings_query = select(
            func.count(Booking.id)
        ).where(
            and_(
                Booking.event_id == event.id,
                Booking.created_at >= datetime.utcnow() - timedelta(days=14),
                Booking.created_at < datetime.utcnow() - timedelta(days=7),
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.PENDING])
            )
        )
        
        previous_bookings_result = await self.db.execute(previous_bookings_query)
        previous_bookings = previous_bookings_result.scalar() or 0

        # Calculate velocity change
        if previous_bookings == 0:
            if recent_bookings > 5:  # High activity with no previous baseline
                return 1.15
            else:
                return 1.0
        
        velocity_ratio = recent_bookings / previous_bookings
        
        if velocity_ratio >= 2.0:
            # Booking velocity doubled - increase price
            return 1.2
        elif velocity_ratio >= 1.5:
            # Booking velocity increased significantly
            return 1.1
        elif velocity_ratio <= 0.5:
            # Booking velocity halved - decrease price
            return 0.9
        else:
            # Normal velocity
            return 1.0

    async def _calculate_waitlist_multiplier(self, event: Event) -> float:
        """Calculate waitlist multiplier based on waitlist size."""
        waitlist_query = select(
            func.count(Waitlist.id)
        ).where(Waitlist.event_id == event.id)
        
        waitlist_result = await self.db.execute(waitlist_query)
        waitlist_size = waitlist_result.scalar() or 0

        if waitlist_size == 0:
            return 1.0
        
        # Calculate waitlist pressure relative to remaining capacity
        if event.available_capacity > 0:
            waitlist_pressure = waitlist_size / event.available_capacity
        else:
            waitlist_pressure = waitlist_size / 10  # Arbitrary baseline for sold-out events

        # Apply waitlist multiplier
        if waitlist_pressure >= 2.0:
            return 1.3  # High waitlist pressure
        elif waitlist_pressure >= 1.0:
            return 1.15  # Moderate waitlist pressure
        elif waitlist_pressure >= 0.5:
            return 1.05  # Some waitlist pressure
        else:
            return 1.0  # Low waitlist pressure

    async def _generate_pricing_reason(
        self,
        event: Event,
        pricing_rule: DynamicPricingRule,
        new_price: Decimal,
        old_price: Decimal
    ) -> str:
        """Generate a human-readable reason for the price change."""
        if new_price == old_price:
            return "Price maintained based on current demand"

        price_change_pct = float((new_price - old_price) / old_price * 100)
        
        # Determine primary reason for price change
        capacity_utilization = (event.total_capacity - event.available_capacity) / event.total_capacity if event.total_capacity > 0 else 0
        days_until_event = (event.event_date - datetime.utcnow()).days

        reasons = []
        
        if capacity_utilization >= pricing_rule.capacity_threshold_high:
            reasons.append("high demand")
        elif capacity_utilization <= pricing_rule.capacity_threshold_low:
            reasons.append("low demand")

        if days_until_event <= 7:
            reasons.append("approaching event date")
        elif days_until_event > 90:
            reasons.append("early bird pricing")

        # Get waitlist size for additional context
        waitlist_query = select(func.count(Waitlist.id)).where(Waitlist.event_id == event.id)
        waitlist_result = await self.db.execute(waitlist_query)
        waitlist_size = waitlist_result.scalar() or 0
        
        if waitlist_size > 0:
            reasons.append(f"waitlist demand ({waitlist_size} waiting)")

        if not reasons:
            reasons.append("market conditions")

        direction = "increased" if price_change_pct > 0 else "decreased"
        reason_text = ", ".join(reasons)
        
        return f"Price {direction} by {abs(price_change_pct):.1f}% due to {reason_text}"