"""FastAPI application setup and configuration."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from evently_booking_platform.config import settings
from evently_booking_platform.api import api_router
from evently_booking_platform.database import init_database, close_database
from evently_booking_platform.middleware import (
    ErrorHandlerMiddleware,
    ValidationMiddleware,
    RateLimiterMiddleware,
    LoggingMiddleware
)
from evently_booking_platform.utils.logging_config import setup_logging

# Set up logging
setup_logging(
    log_level="DEBUG" if settings.debug else "INFO",
    log_file="logs/evently.log" if settings.environment == "production" else None,
    enable_json_logging=settings.environment == "production",
    enable_structured_logging=True
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Evently Booking Platform")
    await init_database()
    logger.info("Database initialized successfully")
    yield
    # Shutdown
    logger.info("Shutting down Evently Booking Platform")
    await close_database()
    logger.info("Database connections closed")

app = FastAPI(
    title="Evently Booking Platform API",
    description="""
    ## Evently Booking Platform
    
    A scalable event booking platform designed to handle high-concurrency ticket booking scenarios.
    
    ### Key Features
    
    * **Event Management**: Create, update, and manage events with detailed information
    * **Ticket Booking**: High-performance booking system with concurrency control
    * **Seat Selection**: Support for venue layouts with specific seat selection
    * **Waitlist Management**: Automatic waitlist handling for sold-out events
    * **User Authentication**: Secure JWT-based authentication system
    * **Admin Analytics**: Comprehensive booking analytics and reporting
    * **Real-time Notifications**: Email notifications for booking updates
    
    ### Authentication
    
    This API uses JWT (JSON Web Token) authentication. To access protected endpoints:
    
    1. Register a new account or login with existing credentials
    2. Use the returned access token in the Authorization header
    3. Format: `Authorization: Bearer <your_access_token>`
    
    ### Rate Limiting
    
    API requests are rate limited to ensure fair usage:
    - Default: 100 requests per minute
    - Burst: 20 requests per second
    
    ### Error Handling
    
    The API returns structured error responses with detailed information:
    
    ```json
    {
      "error": {
        "code": "ERROR_CODE",
        "message": "Human readable error message",
        "details": {
          "field": "Additional error context"
        },
        "suggestions": ["Helpful suggestions"]
      }
    }
    ```
    
    ### Concurrency Safety
    
    The platform is designed to handle high-concurrency booking scenarios:
    - Optimistic locking prevents overselling
    - Database transactions ensure data consistency
    - Redis-based distributed locking for seat selection
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "authentication",
            "description": "User authentication and authorization operations"
        },
        {
            "name": "users",
            "description": "User profile management operations"
        },
        {
            "name": "events",
            "description": "Event management and listing operations"
        },
        {
            "name": "seats",
            "description": "Seat management and venue layout operations"
        },
        {
            "name": "bookings",
            "description": "Ticket booking and reservation operations"
        },
        {
            "name": "waitlist",
            "description": "Waitlist management for sold-out events"
        },
        {
            "name": "analytics",
            "description": "Admin analytics and reporting operations"
        },
        {
            "name": "health",
            "description": "System health and monitoring endpoints"
        }
    ],
    contact={
        "name": "Evently Support",
        "email": "droplakshya@gmail.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    servers=[
        {
            "url": "https://evently-booking-platform-latest.onrender.com",
            "description": "Production server"
        },
        {
            "url": "http://localhost:3000",
            "description": "Development server (HTTP)"
        },
        {
            "url": "https://localhost:3000",
            "description": "Development server (HTTPS)"
        }
    ],
    lifespan=lifespan,
)

# Add comprehensive middleware stack (order matters!)

# 1. Logging middleware (first to capture all requests)
app.add_middleware(
    LoggingMiddleware,
    log_requests=True,
    log_responses=True,
    log_request_body=settings.debug,
    log_response_body=settings.debug
)

# 2. Error handling middleware (catch all errors)
app.add_middleware(
    ErrorHandlerMiddleware,
    debug=settings.debug
)

# 3. Rate limiting middleware
app.add_middleware(
    RateLimiterMiddleware,
    default_limit=100,
    default_window=60,
    burst_limit=20,
    burst_window=1
)

# 4. Request validation middleware
app.add_middleware(
    ValidationMiddleware,
    max_request_size=10 * 1024 * 1024  # 10MB
)

# 5. CORS middleware (last in the middleware stack)
# Configure CORS based on environment
if settings.debug:
    # Development: Allow all origins for easier development
    cors_origins = ["*"]
    cors_allow_credentials = False  # Cannot use credentials with wildcard origins
else:
    # Production: Use configured origins
    cors_origins = settings.cors_origins
    cors_allow_credentials = settings.cors_allow_credentials

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
    expose_headers=settings.cors_expose_headers
)

# Include API routes
app.include_router(api_router)


@app.get("/", tags=["health"])
async def root():
    """
    Root endpoint for API information.
    
    Returns basic information about the API including version and status.
    """
    return {
        "message": "Evently Booking Platform API", 
        "version": "1.0.0",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "status": "operational"
    }


@app.get("/health", tags=["health"])
async def health_check():
    """
    Basic health check endpoint.
    
    Returns the basic health status of the service.
    Use this endpoint for simple uptime monitoring.
    """
    return {"status": "healthy", "service": "evently-booking-platform"}


@app.get("/health/detailed", tags=["health"])
async def detailed_health_check():
    """
    Detailed health check with service dependencies.
    
    Returns comprehensive health information including:
    - Database connectivity
    - Redis cache status
    - External service dependencies
    - System resource usage
    """
    from evently_booking_platform.utils.health_check import get_health_status
    return await get_health_status()


@app.get("/metrics", tags=["health"])
async def get_metrics():
    """
    Get application metrics and performance statistics.
    
    Returns:
    - Circuit breaker statistics
    - Middleware performance metrics
    - Request/response statistics
    - System performance indicators
    """
    from evently_booking_platform.utils.circuit_breaker import _registry
    from evently_booking_platform.middleware.logging import MetricsMiddleware
    
    # Get circuit breaker stats
    circuit_stats = _registry.get_all_stats()
    
    # Get middleware metrics if available
    middleware_metrics = {}
    for middleware in app.user_middleware:
        if isinstance(middleware.cls, type) and issubclass(middleware.cls, MetricsMiddleware):
            middleware_metrics = middleware.cls.get_metrics()
            break
    
    return {
        "circuit_breakers": circuit_stats,
        "middleware": middleware_metrics,
        "timestamp": "2024-01-01T00:00:00Z"  # This would be current timestamp
    }