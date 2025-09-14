"""
Seat model for managing venue seating and seat selection.
"""

import enum
import uuid
from decimal import Decimal
from typing import List, TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .event import Event
    from .seat_booking import SeatBooking


class SeatStatus(enum.Enum):
    """Enumeration for seat status."""
    AVAILABLE = "available"
    HELD = "held"
    BOOKED = "booked"
    BLOCKED = "blocked"


class Seat(Base):
    """Seat model for managing venue seating and seat selection."""
    
    __tablename__ = "seats"
    
    # Foreign key relationships
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Seat location information
    section: Mapped[str] = mapped_column(String(50), nullable=False)
    row: Mapped[str] = mapped_column(String(10), nullable=False)
    number: Mapped[str] = mapped_column(String(10), nullable=False)
    
    # Seat pricing (can differ from base event price)
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), 
        nullable=False,
        default=Decimal('0.00')
    )
    
    # Seat status
    status: Mapped[SeatStatus] = mapped_column(
        Enum(SeatStatus),
        default=SeatStatus.AVAILABLE,
        nullable=False,
        index=True
    )
    
    # Relationships
    event: Mapped["Event"] = relationship("Event", back_populates="seats")
    
    seat_bookings: Mapped[List["SeatBooking"]] = relationship(
        "SeatBooking", 
        back_populates="seat",
        cascade="all, delete-orphan"
    )
    
    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "event_id", "section", "row", "number", 
            name="uq_seats_event_location"
        ),
        CheckConstraint("price >= 0", name="ck_seats_price_non_negative"),
    )
    
    @property
    def is_available(self) -> bool:
        """Check if the seat is available for booking."""
        return self.status == SeatStatus.AVAILABLE
    
    @property
    def seat_identifier(self) -> str:
        """Get a human-readable seat identifier."""
        return f"{self.section}-{self.row}-{self.number}"
    
    def __repr__(self) -> str:
        """String representation of the seat."""
        return (
            f"<Seat(id={self.id}, event_id={self.event_id}, "
            f"location='{self.seat_identifier}', status={self.status.value})>"
        )