"""
Event model for managing events and their capacity.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .booking import Booking
    from .seat import Seat
    from .waitlist import Waitlist


class Event(Base):
    """Event model for managing events and their capacity."""
    
    __tablename__ = "events"
    
    # Event basic information
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    venue: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Event timing
    event_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False,
        index=True
    )
    
    # Capacity management
    total_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    available_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Pricing
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), 
        nullable=False,
        default=Decimal('0.00')
    )
    
    # Seat management
    has_seat_selection: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False
    )
    
    # Optimistic locking for concurrency control
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Event status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    bookings: Mapped[List["Booking"]] = relationship(
        "Booking", 
        back_populates="event",
        cascade="all, delete-orphan"
    )
    
    seats: Mapped[List["Seat"]] = relationship(
        "Seat", 
        back_populates="event",
        cascade="all, delete-orphan"
    )
    
    waitlist_entries: Mapped[List["Waitlist"]] = relationship(
        "Waitlist", 
        back_populates="event",
        cascade="all, delete-orphan"
    )
    
    # Constraints
    __table_args__ = (
        CheckConstraint("total_capacity > 0", name="ck_events_total_capacity_positive"),
        CheckConstraint("available_capacity >= 0", name="ck_events_available_capacity_non_negative"),
        CheckConstraint("available_capacity <= total_capacity", name="ck_events_capacity_consistency"),
        CheckConstraint("price >= 0", name="ck_events_price_non_negative"),
        CheckConstraint("version > 0", name="ck_events_version_positive"),
    )
    
    @property
    def is_sold_out(self) -> bool:
        """Check if the event is sold out."""
        return self.available_capacity == 0
    
    @property
    def capacity_utilization(self) -> float:
        """Get the capacity utilization percentage."""
        if self.total_capacity == 0:
            return 0.0
        return ((self.total_capacity - self.available_capacity) / self.total_capacity) * 100
    
    def __repr__(self) -> str:
        """String representation of the event."""
        return (
            f"<Event(id={self.id}, name='{self.name}', "
            f"date={self.event_date}, capacity={self.available_capacity}/{self.total_capacity})>"
        )