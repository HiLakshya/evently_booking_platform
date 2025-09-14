"""
Booking model for managing ticket reservations.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import User
    from .event import Event
    from .seat_booking import SeatBooking
    from .booking_history import BookingHistory


class BookingStatus(enum.Enum):
    """Enumeration for booking status."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Booking(Base):
    """Booking model for managing ticket reservations."""
    
    __tablename__ = "bookings"
    
    # Foreign key relationships
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Booking details
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), 
        nullable=False,
        default=Decimal('0.00')
    )
    
    # Booking status and timing
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus),
        default=BookingStatus.PENDING,
        nullable=False,
        index=True
    )
    
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="bookings")
    event: Mapped["Event"] = relationship("Event", back_populates="bookings")
    
    seat_bookings: Mapped[List["SeatBooking"]] = relationship(
        "SeatBooking", 
        back_populates="booking",
        cascade="all, delete-orphan"
    )
    
    booking_history: Mapped[List["BookingHistory"]] = relationship(
        "BookingHistory", 
        back_populates="booking",
        cascade="all, delete-orphan"
    )
    
    # Constraints
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_bookings_quantity_positive"),
        CheckConstraint("total_amount >= 0", name="ck_bookings_total_amount_non_negative"),
    )
    
    @property
    def is_active(self) -> bool:
        """Check if the booking is active (confirmed or pending)."""
        return self.status in [BookingStatus.CONFIRMED, BookingStatus.PENDING]
    
    @property
    def is_expired(self) -> bool:
        """Check if the booking has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def __repr__(self) -> str:
        """String representation of the booking."""
        return (
            f"<Booking(id={self.id}, user_id={self.user_id}, "
            f"event_id={self.event_id}, quantity={self.quantity}, status={self.status.value})>"
        )