"""
Authentication-related Pydantic schemas.
"""

from pydantic import BaseModel, EmailStr, Field, field_serializer
from typing import Optional
from uuid import UUID


class UserRegistration(BaseModel):
    """Schema for user registration."""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)


class UserLogin(BaseModel):
    """Schema for user login."""
    email: EmailStr
    password: str


class UserProfile(BaseModel):
    """Schema for user profile information."""
    id: UUID
    email: str
    first_name: str
    last_name: str
    is_admin: bool
    is_active: bool
    
    @field_serializer('id')
    def serialize_id(self, value: UUID) -> str:
        return str(value)
    
    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    """Schema for updating user profile."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)


class PasswordChange(BaseModel):
    """Schema for changing password."""
    current_password: str
    new_password: str = Field(..., min_length=8, description="Password must be at least 8 characters")


class TokenResponse(BaseModel):
    """Schema for token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfile


# Alias for consistency with other schemas
UserResponse = UserProfile