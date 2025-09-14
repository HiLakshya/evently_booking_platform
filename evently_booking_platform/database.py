"""
Database connection management and session handling.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine,
)
# QueuePool is not needed for async engines

from .config import get_settings
from .models.base import Base
from .cache import init_cache, close_cache

logger = logging.getLogger(__name__)

# Global engine and session factory
engine: AsyncEngine | None = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_database_engine() -> AsyncEngine:
    """Create and configure the database engine with connection pooling."""
    settings = get_settings()
    
    return create_async_engine(
        settings.database_url,
        # Connection pool configuration for concurrent access
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,  # Validate connections before use
        pool_recycle=3600,   # Recycle connections every hour
        # Echo SQL queries in development
        echo=settings.debug,
        # Connection arguments
        connect_args={
            "server_settings": {
                "application_name": "evently_booking_platform",
            }
        }
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create session factory for database sessions."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
        autocommit=False,
    )


async def init_database() -> None:
    """Initialize database connection and create tables."""
    global engine, async_session_factory
    
    logger.info("Initializing database connection...")
    
    # Create engine and session factory
    engine = create_database_engine()
    async_session_factory = create_session_factory(engine)
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Initialize Redis cache
    await init_cache()
    
    logger.info("Database and cache initialized successfully")


async def close_database() -> None:
    """Close database connections."""
    global engine
    
    if engine:
        logger.info("Closing database connections...")
        await engine.dispose()
        logger.info("Database connections closed")
    
    # Close Redis cache
    await close_cache()


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session with automatic cleanup.
    
    Usage:
        async with get_db_session() as session:
            # Use session here
            result = await session.execute(query)
    """
    if async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for getting database sessions.
    
    Usage in FastAPI endpoints:
        @app.get("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_db_session_dependency)):
            # Use db session here
    """
    async with get_db_session() as session:
        yield session


class DatabaseManager:
    """Database manager for handling connections and sessions."""
    
    def __init__(self):
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
    
    async def initialize(self) -> None:
        """Initialize the database manager."""
        self.engine = create_database_engine()
        self.session_factory = create_session_factory(self.engine)
        
        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Database manager initialized")
    
    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database manager closed")
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        if self.session_factory is None:
            raise RuntimeError("Database manager not initialized")
        
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


# Global database manager instance
db_manager = DatabaseManager()


# FastAPI dependency function
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for getting database sessions.
    
    Usage in FastAPI endpoints:
        @app.get("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            # Use db session here
    """
    async with get_db_session() as session:
        yield session