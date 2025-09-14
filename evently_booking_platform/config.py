"""Configuration settings for the Evently Booking Platform."""

from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
   
    # Database Configuration
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/evently_db"
    database_pool_size: int = 20
    database_max_overflow: int = 30
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 20
    
    # Celery Configuration
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    
    # JWT Configuration
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Application Configuration
    debug: bool = False
    environment: str = "development"
    
    # Email Configuration (for notifications)
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True
    
    # Booking Configuration
    booking_hold_timeout_minutes: int = 15
    max_booking_quantity: int = 10
    
    # Waitlist Configuration
    waitlist_notification_timeout_hours: int = 24
    
    # Error Handling Configuration
    enable_circuit_breakers: bool = True
    enable_retry_mechanisms: bool = True
    max_retry_attempts: int = 3
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60
    
    # Rate Limiting Configuration
    enable_rate_limiting: bool = True
    default_rate_limit: int = 100
    default_rate_window: int = 60
    burst_rate_limit: int = 20
    burst_rate_window: int = 1
    
    # CORS Configuration
    cors_origins: list[str] = [
        "http://localhost:3000", 
        "http://localhost:3001", 
        "http://127.0.0.1:3000", 
        "http://127.0.0.1:3001",
        "https://localhost:3000",
        "https://localhost:3001", 
        "https://127.0.0.1:3000",
        "https://127.0.0.1:3001",
        "https://evently-booking-platform-latest.onrender.com",
        "https://evently-booking-platform-latest.onrender.com:3000"
    ]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    cors_allow_headers: list[str] = ["*"]
    cors_expose_headers: list[str] = ["X-Request-ID", "X-Process-Time", "X-RateLimit-*"]
    
    # Logging Configuration
    log_level: str = "INFO"
    enable_json_logging: bool = False
    enable_request_logging: bool = True
    enable_performance_logging: bool = True
    log_sensitive_data: bool = False
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8"
    }


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance for backward compatibility
settings = get_settings()