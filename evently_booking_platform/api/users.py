"""
User management API endpoints (admin only).
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.user import User
from ..schemas.auth import UserProfile
from ..services.user_service import UserService
from ..utils.dependencies import get_current_admin_user


router = APIRouter(prefix="/users", tags=["user-management"])


@router.get("/{user_id}", response_model=UserProfile)
async def get_user_by_id(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin_user)
) -> Any:
    """
    Get a user by ID (admin only).
    
    Args:
        user_id: The user ID
        db: Database session
        _: Admin user (for authorization)
        
    Returns:
        User profile information
        
    Raises:
        HTTPException: If user not found
    """
    user_service = UserService(db)
    user = await user_service.get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserProfile.model_validate(user)


@router.post("/{user_id}/deactivate", status_code=status.HTTP_200_OK)
async def deactivate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin_user)
) -> Any:
    """
    Deactivate a user account (admin only).
    
    Args:
        user_id: The user ID
        db: Database session
        _: Admin user (for authorization)
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If user not found
    """
    user_service = UserService(db)
    success = await user_service.deactivate_user(user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {"message": "User deactivated successfully"}


@router.post("/{user_id}/activate", status_code=status.HTTP_200_OK)
async def activate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin_user)
) -> Any:
    """
    Activate a user account (admin only).
    
    Args:
        user_id: The user ID
        db: Database session
        _: Admin user (for authorization)
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If user not found
    """
    user_service = UserService(db)
    success = await user_service.activate_user(user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {"message": "User activated successfully"}