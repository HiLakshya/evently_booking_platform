"""
Event recommendation service based on user history and preferences.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any, Set
from uuid import UUID
import math

from sqlalchemy import select, and_, or_, func, desc, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from evently_booking_platform.models import (
    Event, Booking, BookingStatus, User, Waitlist
)
from evently_booking_platform.schemas.advanced_analytics import (
    EventRecommendation, EventRecommendationRequest, EventRecommendationResponse
)
from evently_booking_platform.cache import get_cache, CacheKeyBuilder

logger = logging.getLogger(__name__)


class EventRecommendationService:
    """Service for intelligent event recommendations."""

    def __init__(self, db: AsyncSession):
        """Initialize the event recommendation service."""
        self.db = db
        self.cache = get_cache()

    async def get_event_recommendations(
        self,
        request: EventRecommendationRequest
    ) -> EventRecommendationResponse:
        """Get personalized event recommendations for a user."""
        # Get user's booking history and preferences
        user_profile = await self._build_user_profile(request.user_id)
        
        # Get available events
        available_events = await self._get_available_events(request)
        
        if not available_events:
            return EventRecommendationResponse(
                user_id=request.user_id,
                recommendations=[],
                algorithm_used="no_events_available",
                personalization_score=0.0
            )

        # Calculate recommendations using multiple algorithms
        recommendations = []
        
        for event in available_events:
            # Calculate different recommendation scores
            similarity_score = await self._calculate_similarity_score(event, user_profile)
            popularity_score = await self._calculate_popularity_score(event)
            availability_score = self._calculate_availability_score(event)
            
            # Combine scores with weights
            final_score = (
                similarity_score * 0.5 +  # 50% weight on similarity to past bookings
                popularity_score * 0.3 +  # 30% weight on popularity
                availability_score * 0.2  # 20% weight on availability
            )
            
            reasons = self._generate_recommendation_reasons(
                event, user_profile, similarity_score, popularity_score
            )
            
            recommendation = EventRecommendation(
                event_id=event.id,
                event_name=event.name,
                venue=event.venue,
                event_date=event.event_date,
                price=event.price,
                score=final_score,
                reasons=reasons,
                similarity_to_past_bookings=similarity_score,
                popularity_score=popularity_score,
                availability_score=availability_score
            )
            
            recommendations.append(recommendation)

        # Sort by score and limit results
        recommendations.sort(key=lambda x: x.score, reverse=True)
        recommendations = recommendations[:request.limit]

        # Calculate personalization score
        personalization_score = self._calculate_personalization_score(user_profile)

        return EventRecommendationResponse(
            user_id=request.user_id,
            recommendations=recommendations,
            algorithm_used="hybrid_collaborative_content",
            personalization_score=personalization_score
        )

    async def _build_user_profile(self, user_id: UUID) -> Dict[str, Any]:
        """Build a user profile based on booking history."""
        # Get user's booking history
        bookings_query = select(
            Event.venue,
            Event.price,
            Event.event_date,
            Event.name,
            Booking.created_at,
            Booking.status
        ).select_from(
            Booking
        ).join(
            Event, Booking.event_id == Event.id
        ).where(
            and_(
                Booking.user_id == user_id,
                Booking.status == BookingStatus.CONFIRMED
            )
        ).order_by(
            Booking.created_at.desc()
        )

        bookings_result = await self.db.execute(bookings_query)
        bookings = bookings_result.fetchall()

        if not bookings:
            return {
                'preferred_venues': [],
                'average_price': 0,
                'booking_frequency': 0,
                'preferred_times': [],
                'event_keywords': [],
                'booking_count': 0
            }

        # Analyze preferences
        venues = [booking.venue for booking in bookings]
        prices = [float(booking.price) for booking in bookings]
        event_names = [booking.name.lower() for booking in bookings]
        
        # Extract keywords from event names
        keywords = set()
        for name in event_names:
            words = name.split()
            keywords.update(word for word in words if len(word) > 3)

        # Calculate booking frequency (bookings per month)
        if bookings:
            first_booking = min(booking.created_at for booking in bookings)
            months_active = max(1, (datetime.utcnow() - first_booking).days / 30)
            booking_frequency = len(bookings) / months_active
        else:
            booking_frequency = 0

        # Preferred booking times (day of week, time of day)
        preferred_times = []
        for booking in bookings:
            event_date = booking.event_date
            preferred_times.append({
                'day_of_week': event_date.weekday(),
                'hour': event_date.hour
            })

        return {
            'preferred_venues': list(set(venues)),
            'average_price': sum(prices) / len(prices) if prices else 0,
            'booking_frequency': booking_frequency,
            'preferred_times': preferred_times,
            'event_keywords': list(keywords)[:10],  # Top 10 keywords
            'booking_count': len(bookings)
        }

    async def _get_available_events(
        self,
        request: EventRecommendationRequest
    ) -> List[Event]:
        """Get available events based on request filters."""
        query = select(Event).where(
            and_(
                Event.event_date > datetime.utcnow(),
                Event.available_capacity > 0,
                Event.is_active == True
            )
        )

        # Apply filters
        if request.max_price:
            query = query.where(Event.price <= request.max_price)

        if request.date_range_start:
            query = query.where(Event.event_date >= request.date_range_start)

        if request.date_range_end:
            query = query.where(Event.event_date <= request.date_range_end)

        # Category filters would be applied here if we had event categories
        # if request.include_categories:
        #     query = query.where(Event.category.in_(request.include_categories))

        query = query.order_by(Event.event_date).limit(100)  # Limit for performance

        result = await self.db.execute(query)
        return result.scalars().all()

    async def _calculate_similarity_score(
        self,
        event: Event,
        user_profile: Dict[str, Any]
    ) -> float:
        """Calculate similarity score based on user's past preferences."""
        if user_profile['booking_count'] == 0:
            return 0.5  # Neutral score for new users

        score = 0.0

        # Venue preference
        if event.venue in user_profile['preferred_venues']:
            score += 0.3

        # Price preference
        if user_profile['average_price'] > 0:
            price_diff = abs(float(event.price) - user_profile['average_price'])
            max_price_diff = user_profile['average_price']  # Normalize by average price
            price_similarity = max(0, 1 - (price_diff / max_price_diff)) if max_price_diff > 0 else 0.5
            score += price_similarity * 0.3

        # Event name keyword matching
        event_words = set(event.name.lower().split())
        keyword_matches = len(event_words.intersection(set(user_profile['event_keywords'])))
        if user_profile['event_keywords']:
            keyword_score = keyword_matches / len(user_profile['event_keywords'])
            score += keyword_score * 0.2

        # Time preference (day of week, time of day)
        if user_profile['preferred_times']:
            event_day = event.event_date.weekday()
            event_hour = event.event_date.hour
            
            time_matches = sum(
                1 for pref in user_profile['preferred_times']
                if abs(pref['day_of_week'] - event_day) <= 1 and
                   abs(pref['hour'] - event_hour) <= 2
            )
            
            time_score = time_matches / len(user_profile['preferred_times'])
            score += time_score * 0.2

        return min(score, 1.0)

    async def _calculate_popularity_score(self, event: Event) -> float:
        """Calculate popularity score based on booking activity."""
        # Get booking count for this event
        booking_count_query = select(
            func.count(Booking.id)
        ).where(
            and_(
                Booking.event_id == event.id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.PENDING])
            )
        )

        booking_count_result = await self.db.execute(booking_count_query)
        booking_count = booking_count_result.scalar() or 0

        # Get waitlist count
        waitlist_count_query = select(
            func.count(Waitlist.id)
        ).where(Waitlist.event_id == event.id)

        waitlist_count_result = await self.db.execute(waitlist_count_query)
        waitlist_count = waitlist_count_result.scalar() or 0

        # Calculate popularity based on bookings and capacity utilization
        capacity_utilization = (event.total_capacity - event.available_capacity) / event.total_capacity
        
        # Normalize booking count (assume max 1000 bookings for normalization)
        normalized_bookings = min(booking_count / 100, 1.0)
        
        # Waitlist indicates high demand
        waitlist_factor = min(waitlist_count / 50, 0.3)  # Max 0.3 bonus for waitlist

        popularity_score = (capacity_utilization * 0.6 + 
                          normalized_bookings * 0.3 + 
                          waitlist_factor)

        return min(popularity_score, 1.0)

    def _calculate_availability_score(self, event: Event) -> float:
        """Calculate availability score (higher for better availability)."""
        if event.total_capacity == 0:
            return 0.0

        availability_ratio = event.available_capacity / event.total_capacity
        
        # Score higher for events with good availability (not too empty, not too full)
        if 0.3 <= availability_ratio <= 0.8:
            return 1.0  # Sweet spot
        elif availability_ratio > 0.8:
            return 0.7  # Too empty might indicate low quality
        elif availability_ratio > 0.1:
            return 0.8  # Some urgency but still available
        else:
            return 0.3  # Very limited availability

    def _generate_recommendation_reasons(
        self,
        event: Event,
        user_profile: Dict[str, Any],
        similarity_score: float,
        popularity_score: float
    ) -> List[str]:
        """Generate human-readable reasons for the recommendation."""
        reasons = []

        # Venue-based reasons
        if event.venue in user_profile['preferred_venues']:
            reasons.append(f"You've enjoyed events at {event.venue} before")

        # Price-based reasons
        if user_profile['average_price'] > 0:
            price_diff_pct = abs(float(event.price) - user_profile['average_price']) / user_profile['average_price']
            if price_diff_pct < 0.2:
                reasons.append("Price matches your typical spending")
            elif float(event.price) < user_profile['average_price'] * 0.8:
                reasons.append("Great value compared to your usual bookings")

        # Popularity-based reasons
        if popularity_score > 0.7:
            reasons.append("Highly popular event with strong demand")
        elif popularity_score > 0.5:
            reasons.append("Growing popularity among other users")

        # Keyword matching
        event_words = set(event.name.lower().split())
        matching_keywords = event_words.intersection(set(user_profile['event_keywords']))
        if matching_keywords:
            reasons.append(f"Similar to events you've booked: {', '.join(list(matching_keywords)[:2])}")

        # Availability reasons
        availability_ratio = event.available_capacity / event.total_capacity if event.total_capacity > 0 else 0
        if availability_ratio < 0.3:
            reasons.append("Limited availability - book soon!")
        elif availability_ratio > 0.8:
            reasons.append("Plenty of seats available")

        # Default reason if no specific reasons found
        if not reasons:
            reasons.append("Recommended based on your preferences")

        return reasons[:3]  # Limit to top 3 reasons

    def _calculate_personalization_score(self, user_profile: Dict[str, Any]) -> float:
        """Calculate how personalized the recommendations are."""
        if user_profile['booking_count'] == 0:
            return 0.1  # Very low personalization for new users

        # More bookings = better personalization
        booking_factor = min(user_profile['booking_count'] / 10, 0.5)  # Max 0.5 from booking count
        
        # Diversity of preferences
        venue_diversity = min(len(user_profile['preferred_venues']) / 5, 0.3)  # Max 0.3 from venue diversity
        keyword_diversity = min(len(user_profile['event_keywords']) / 10, 0.2)  # Max 0.2 from keywords

        personalization_score = booking_factor + venue_diversity + keyword_diversity
        return min(personalization_score, 1.0)