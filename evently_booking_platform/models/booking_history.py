"""
BookingHistory model for tracking booking audit trail.
"""

import enum
import uuid
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .booking import Booking


class BookingAction(enum.Enum):
    """Enumeration for booking actions."""
    CREATED = "created"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    MODIFIED = "modified"


class BookingHistory(Base):
    """BookingHistory model for tracking booking audit trail."""
    
    __tablename__ = "booking_history"
    
    # Foreign key relationships
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Action details
    action: Mapped[BookingAction] = mapped_column(
        Enum(BookingAction),
        nullable=False,
        index=True
    )
    
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Optional user context (for admin actions)
    performed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="booking_history")
    
    def __repr__(self) -> str:
        """String representation of the booking history entry."""
        return (
            f"<BookingHistory(id={self.id}, booking_id={self.booking_id}, "
            f"action={self.action.value}, created_at={self.created_at})>"
        )