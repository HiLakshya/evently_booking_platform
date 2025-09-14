"""
Authentication API endpoints.
"""

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.user import User
from ..schemas.auth import (
    UserRegistration, 
    UserLogin, 
    UserProfile, 
    UserProfileUpdate,
    PasswordChange,
    TokenResponse
)
from ..services.user_service import UserService
from ..utils.auth import create_access_token
from ..utils.dependencies import get_current_active_user


router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserRegistration,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Register a new user.
    
    Args:
        user_data: User registration data
        db: Database session
        
    Returns:
        Token response with user information
        
    Raises:
        HTTPException: If email already exists or validation fails
    """
    user_service = UserService(db)
    
    try:
        user = await user_service.create_user(user_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=access_token_expires
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserProfile.model_validate(user)
    )


@router.post("/login", response_model=TokenResponse)
async def login_user(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Authenticate user and return access token.
    
    Args:
        login_data: User login credentials
        db: Database session
        
    Returns:
        Token response with user information
        
    Raises:
        HTTPException: If credentials are invalid
    """
    user_service = UserService(db)
    
    user = await user_service.authenticate_user(
        login_data.email, 
        login_data.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=access_token_expires
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserProfile.model_validate(user)
    )


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get current user's profile.
    
    Args:
        current_user: The authenticated user
        
    Returns:
        User profile information
    """
    return UserProfile.model_validate(current_user)


@router.put("/me", response_model=UserProfile)
async def update_current_user_profile(
    update_data: UserProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Update current user's profile.
    
    Args:
        update_data: Profile update data
        current_user: The authenticated user
        db: Database session
        
    Returns:
        Updated user profile
        
    Raises:
        HTTPException: If update fails
    """
    user_service = UserService(db)
    
    updated_user = await user_service.update_user_profile(
        current_user.id, 
        update_data
    )
    
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserProfile.model_validate(updated_user)


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Change current user's password.
    
    Args:
        password_data: Password change data
        current_user: The authenticated user
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If current password is incorrect
    """
    user_service = UserService(db)
    
    success = await user_service.change_password(
        current_user.id,
        password_data.current_password,
        password_data.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    return {"message": "Password changed successfully"}