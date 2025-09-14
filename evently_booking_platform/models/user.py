"""
User model for authentication and user management.
"""

from typing import List, TYPE_CHECKING

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from ..utils.auth import get_password_hash, verify_password

if TYPE_CHECKING:
    from .booking import Booking
    from .waitlist import Waitlist


class User(Base):
    """User model for authentication and profile management."""
    
    __tablename__ = "users"
    
    # User identification and authentication
    email: Mapped[str] = mapped_column(
        String(255), 
        unique=True, 
        nullable=False,
        index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # User profile information
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # User permissions
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    bookings: Mapped[List["Booking"]] = relationship(
        "Booking", 
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    waitlist_entries: Mapped[List["Waitlist"]] = relationship(
        "Waitlist", 
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
    )
    
    @property
    def full_name(self) -> str:
        """Get the user's full name."""
        return f"{self.first_name} {self.last_name}"
    
    def set_password(self, password: str) -> None:
        """Hash and set the user's password."""
        self.password_hash = get_password_hash(password)
    
    def verify_password(self, password: str) -> bool:
        """Verify the user's password against the stored hash."""
        return verify_password(password, self.password_hash)
    
    def __repr__(self) -> str:
        """String representation of the user."""
        return f"<User(id={self.id}, email='{self.email}', name='{self.full_name}')>"