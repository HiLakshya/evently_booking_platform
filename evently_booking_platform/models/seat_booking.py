"""
SeatBooking model for linking bookings to specific seats.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .booking import Booking
    from .seat import Seat


class SeatBooking(Base):
    """SeatBooking model for linking bookings to specific seats."""
    
    __tablename__ = "seat_bookings"
    
    # Foreign key relationships
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    seat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("seats.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="seat_bookings")
    seat: Mapped["Seat"] = relationship("Seat", back_populates="seat_bookings")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "booking_id", "seat_id", 
            name="uq_seat_bookings_booking_seat"
        ),
    )
    
    def __repr__(self) -> str:
        """String representation of the seat booking."""
        return (
            f"<SeatBooking(id={self.id}, booking_id={self.booking_id}, "
            f"seat_id={self.seat_id})>"
        )