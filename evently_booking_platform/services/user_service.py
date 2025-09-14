"""
User service for handling user-related operations.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from ..models.user import User
from ..schemas.auth import UserRegistration, UserProfileUpdate
from ..utils.auth import get_password_hash


class UserService:
    """Service class for user operations."""
    
    def __init__(self, db: AsyncSession):
        """
        Initialize the user service.
        
        Args:
            db: Database session
        """
        self.db = db
    
    async def create_user(self, user_data: UserRegistration) -> User:
        """
        Create a new user.
        
        Args:
            user_data: User registration data
            
        Returns:
            The created user
            
        Raises:
            ValueError: If email already exists
        """
        # Check if user already exists
        existing_user = await self.get_user_by_email(user_data.email)
        if existing_user:
            raise ValueError("Email already registered")
        
        # Create new user
        user = User(
            email=user_data.email,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            password_hash=get_password_hash(user_data.password)
        )
        
        try:
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            return user
        except IntegrityError:
            await self.db.rollback()
            raise ValueError("Email already registered")
    
    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """
        Get a user by ID.
        
        Args:
            user_id: The user ID
            
        Returns:
            The user if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get a user by email.
        
        Args:
            email: The user email
            
        Returns:
            The user if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate a user with email and password.
        
        Args:
            email: The user email
            password: The user password
            
        Returns:
            The user if authentication successful, None otherwise
        """
        user = await self.get_user_by_email(email)
        if not user:
            return None
        
        if not user.verify_password(password):
            return None
        
        return user
    
    async def update_user_profile(
        self, 
        user_id: UUID, 
        update_data: UserProfileUpdate
    ) -> Optional[User]:
        """
        Update a user's profile.
        
        Args:
            user_id: The user ID
            update_data: The update data
            
        Returns:
            The updated user if found, None otherwise
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        
        # Update only provided fields
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(user, field, value)
        
        await self.db.commit()
        await self.db.refresh(user)
        return user
    
    async def change_password(
        self, 
        user_id: UUID, 
        current_password: str, 
        new_password: str
    ) -> bool:
        """
        Change a user's password.
        
        Args:
            user_id: The user ID
            current_password: The current password
            new_password: The new password
            
        Returns:
            True if password changed successfully, False otherwise
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        
        # Verify current password
        if not user.verify_password(current_password):
            return False
        
        # Set new password
        user.set_password(new_password)
        await self.db.commit()
        return True
    
    async def deactivate_user(self, user_id: UUID) -> bool:
        """
        Deactivate a user account.
        
        Args:
            user_id: The user ID
            
        Returns:
            True if user deactivated successfully, False otherwise
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        
        user.is_active = False
        await self.db.commit()
        return True
    
    async def activate_user(self, user_id: UUID) -> bool:
        """
        Activate a user account.
        
        Args:
            user_id: The user ID
            
        Returns:
            True if user activated successfully, False otherwise
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        
        user.is_active = True
        await self.db.commit()
        return True