"""
Seat recommendation service using algorithms to suggest optimal seats.
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from decimal import Decimal
import math

from sqlalchemy import select, and_, or_, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evently_booking_platform.models import (
    Event, Seat, SeatStatus, SeatBooking, Booking, BookingStatus, User
)
from evently_booking_platform.schemas.advanced_analytics import (
    SeatRecommendation, SeatRecommendationRequest, SeatRecommendationResponse
)
from evently_booking_platform.utils.exceptions import EventNotFoundError
from evently_booking_platform.cache import get_cache, CacheKeyBuilder

logger = logging.getLogger(__name__)


class SeatRecommendationService:
    """Service for intelligent seat recommendations."""

    def __init__(self, db: AsyncSession):
        """Initialize the seat recommendation service."""
        self.db = db
        self.cache = get_cache()

    async def get_seat_recommendations(
        self,
        request: SeatRecommendationRequest
    ) -> SeatRecommendationResponse:
        """Get seat recommendations based on user preferences and algorithms."""
        # Verify event exists
        event_query = select(Event).where(Event.id == request.event_id)
        event_result = await self.db.execute(event_query)
        event = event_result.scalar_one_or_none()
        
        if not event:
            raise EventNotFoundError(f"Event {request.event_id} not found")

        # Get available seats
        seats_query = select(Seat).where(
            and_(
                Seat.event_id == request.event_id,
                Seat.status == SeatStatus.AVAILABLE
            )
        )
        
        if request.max_price:
            seats_query = seats_query.where(Seat.price <= request.max_price)
        
        if request.preferred_sections:
            seats_query = seats_query.where(Seat.section.in_(request.preferred_sections))

        seats_result = await self.db.execute(seats_query)
        available_seats = seats_result.scalars().all()

        if not available_seats:
            return SeatRecommendationResponse(
                event_id=request.event_id,
                recommendations=[],
                total_options=0,
                algorithm_used="no_seats_available"
            )

        # Get user's booking history for personalization
        user_history = await self._get_user_booking_history(request.user_id)
        
        # Apply recommendation algorithms
        if request.quantity == 1:
            recommendations = await self._recommend_single_seats(
                available_seats, user_history, request
            )
            algorithm_used = "single_seat_optimization"
        else:
            recommendations = await self._recommend_group_seats(
                available_seats, user_history, request
            )
            algorithm_used = "group_seat_optimization"

        return SeatRecommendationResponse(
            event_id=request.event_id,
            recommendations=recommendations,
            total_options=len(recommendations),
            algorithm_used=algorithm_used
        )

    async def _get_user_booking_history(self, user_id: UUID) -> Dict[str, Any]:
        """Get user's booking history for personalization."""
        history_query = select(
            Seat.section,
            Seat.price,
            func.count(SeatBooking.id).label('booking_count')
        ).select_from(
            SeatBooking
        ).join(
            Booking, SeatBooking.booking_id == Booking.id
        ).join(
            Seat, SeatBooking.seat_id == Seat.id
        ).where(
            and_(
                Booking.user_id == user_id,
                Booking.status == BookingStatus.CONFIRMED
            )
        ).group_by(
            Seat.section, Seat.price
        ).order_by(
            func.count(SeatBooking.id).desc()
        )

        history_result = await self.db.execute(history_query)
        history_rows = history_result.fetchall()

        preferred_sections = []
        price_preferences = []
        
        for row in history_rows:
            preferred_sections.append(row.section)
            price_preferences.append(float(row.price))

        return {
            'preferred_sections': preferred_sections[:3],  # Top 3 preferred sections
            'average_price': sum(price_preferences) / len(price_preferences) if price_preferences else 0,
            'booking_count': len(history_rows)
        }

    async def _recommend_single_seats(
        self,
        available_seats: List[Seat],
        user_history: Dict[str, Any],
        request: SeatRecommendationRequest
    ) -> List[List[SeatRecommendation]]:
        """Recommend single seats using multiple criteria."""
        recommendations = []
        
        for seat in available_seats:
            score = await self._calculate_seat_score(seat, user_history, request)
            reasons = self._generate_recommendation_reasons(seat, user_history, score)
            
            recommendation = SeatRecommendation(
                seat_id=seat.id,
                section=seat.section,
                row=seat.row,
                number=seat.number,
                price=seat.price,
                score=score,
                reasons=reasons
            )
            
            recommendations.append([recommendation])  # Single seat groups

        # Sort by score and return top recommendations
        recommendations.sort(key=lambda x: x[0].score, reverse=True)
        return recommendations[:20]  # Top 20 recommendations

    async def _recommend_group_seats(
        self,
        available_seats: List[Seat],
        user_history: Dict[str, Any],
        request: SeatRecommendationRequest
    ) -> List[List[SeatRecommendation]]:
        """Recommend groups of seats for multiple people."""
        recommendations = []
        
        # Group seats by section and row for contiguous seating
        seat_groups = {}
        for seat in available_seats:
            key = f"{seat.section}_{seat.row}"
            if key not in seat_groups:
                seat_groups[key] = []
            seat_groups[key].append(seat)

        # Find contiguous seat groups
        for group_key, seats in seat_groups.items():
            if len(seats) < request.quantity:
                continue
                
            # Sort seats by number to find contiguous groups
            seats.sort(key=lambda s: int(s.number) if s.number.isdigit() else 999)
            
            # Find contiguous sequences
            contiguous_groups = self._find_contiguous_seats(seats, request.quantity)
            
            for group in contiguous_groups:
                group_score = sum(
                    await self._calculate_seat_score(seat, user_history, request) 
                    for seat in group
                ) / len(group)
                
                # Bonus for contiguous seating
                group_score += 0.2
                
                seat_recommendations = []
                for seat in group:
                    reasons = self._generate_recommendation_reasons(seat, user_history, group_score)
                    reasons.append("Part of contiguous seating group")
                    
                    seat_recommendations.append(SeatRecommendation(
                        seat_id=seat.id,
                        section=seat.section,
                        row=seat.row,
                        number=seat.number,
                        price=seat.price,
                        score=group_score,
                        reasons=reasons
                    ))
                
                recommendations.append(seat_recommendations)

        # Sort by average group score
        recommendations.sort(key=lambda group: sum(s.score for s in group) / len(group), reverse=True)
        return recommendations[:10]  # Top 10 group recommendations

    def _find_contiguous_seats(self, seats: List[Seat], quantity: int) -> List[List[Seat]]:
        """Find contiguous seat groups of the specified quantity."""
        contiguous_groups = []
        
        for i in range(len(seats) - quantity + 1):
            group = []
            current_num = None
            
            for j in range(i, min(i + quantity, len(seats))):
                seat = seats[j]
                seat_num = int(seat.number) if seat.number.isdigit() else None
                
                if seat_num is None:
                    break
                    
                if current_num is None:
                    current_num = seat_num
                    group.append(seat)
                elif seat_num == current_num + 1:
                    current_num = seat_num
                    group.append(seat)
                else:
                    break
            
            if len(group) == quantity:
                contiguous_groups.append(group)
        
        return contiguous_groups

    async def _calculate_seat_score(
        self,
        seat: Seat,
        user_history: Dict[str, Any],
        request: SeatRecommendationRequest
    ) -> float:
        """Calculate recommendation score for a seat."""
        score = 0.5  # Base score
        
        # Price preference scoring
        if user_history.get('average_price', 0) > 0:
            price_diff = abs(float(seat.price) - user_history['average_price'])
            max_price = float(request.max_price) if request.max_price else 1000
            price_score = 1 - (price_diff / max_price)
            score += price_score * 0.3
        
        # Section preference scoring
        if seat.section in user_history.get('preferred_sections', []):
            score += 0.3
        
        # Row preference (middle rows often preferred)
        if seat.row.isdigit():
            row_num = int(seat.row)
            # Assume rows 5-15 are optimal (middle of venue)
            if 5 <= row_num <= 15:
                score += 0.2
            elif row_num < 5:  # Front rows
                score += 0.1
        
        # Accessibility bonus
        if request.accessibility_required and 'accessible' in seat.section.lower():
            score += 0.4
        
        # Value scoring (lower price relative to section average)
        # This would require more complex venue data
        
        return min(score, 1.0)  # Cap at 1.0

    def _generate_recommendation_reasons(
        self,
        seat: Seat,
        user_history: Dict[str, Any],
        score: float
    ) -> List[str]:
        """Generate human-readable reasons for the recommendation."""
        reasons = []
        
        if seat.section in user_history.get('preferred_sections', []):
            reasons.append(f"You've previously booked in {seat.section} section")
        
        if score > 0.8:
            reasons.append("Excellent seat with great view")
        elif score > 0.6:
            reasons.append("Good seat with decent view")
        
        if seat.row.isdigit():
            row_num = int(seat.row)
            if row_num <= 5:
                reasons.append("Close to the stage/action")
            elif 5 < row_num <= 15:
                reasons.append("Optimal viewing distance")
        
        price_range = float(seat.price)
        if price_range < 50:
            reasons.append("Budget-friendly option")
        elif price_range > 200:
            reasons.append("Premium seating experience")
        
        if not reasons:
            reasons.append("Available seat matching your criteria")
        
        return reasons