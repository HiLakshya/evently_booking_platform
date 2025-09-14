"""
Waitlist model for managing event waitlists.
"""

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import User
    from .event import Event


class WaitlistStatus(enum.Enum):
    """Enumeration for waitlist status."""
    ACTIVE = "active"
    NOTIFIED = "notified"
    EXPIRED = "expired"
    CONVERTED = "converted"


class Waitlist(Base):
    """Waitlist model for managing event waitlists."""
    
    __tablename__ = "waitlist"
    
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
    
    # Waitlist details
    requested_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Waitlist status
    status: Mapped[WaitlistStatus] = mapped_column(
        Enum(WaitlistStatus),
        default=WaitlistStatus.ACTIVE,
        nullable=False,
        index=True
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="waitlist_entries")
    event: Mapped["Event"] = relationship("Event", back_populates="waitlist_entries")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "user_id", "event_id", 
            name="uq_waitlist_user_event"
        ),
        CheckConstraint("requested_quantity > 0", name="ck_waitlist_quantity_positive"),
        CheckConstraint("position > 0", name="ck_waitlist_position_positive"),
    )
    
    @property
    def is_active(self) -> bool:
        """Check if the waitlist entry is active."""
        return self.status == WaitlistStatus.ACTIVE
    
    def __repr__(self) -> str:
        """String representation of the waitlist entry."""
        return (
            f"<Waitlist(id={self.id}, user_id={self.user_id}, "
            f"event_id={self.event_id}, position={self.position}, status={self.status.value})>"
        )