"""
Redis caching layer for performance optimization.
"""

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
import asyncio

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import RedisError
from redis.exceptions import ConnectionError as RedisConnectionError

from .config import get_settings

logger = logging.getLogger(__name__)

# Global Redis connection pool
redis_pool: Optional[redis.ConnectionPool] = None
redis_client: Optional[Redis] = None


class CacheKeyBuilder:
    """Helper class for building consistent cache keys."""

    @staticmethod
    def event_list(filters_hash: str, page: int, size: int) -> str:
        """Build cache key for event listings."""
        return f"events:list:{filters_hash}:{page}:{size}"

    @staticmethod
    def event_detail(event_id: str) -> str:
        """Build cache key for event details."""
        return f"event:detail:{event_id}"

    @staticmethod
    def seat_map(event_id: str) -> str:
        """Build cache key for seat maps."""
        return f"seats:map:{event_id}"

    @staticmethod
    def seat_availability(event_id: str) -> str:
        """Build cache key for seat availability."""
        return f"seats:availability:{event_id}"

    @staticmethod
    def popular_events(limit: int) -> str:
        """Build cache key for popular events."""
        return f"events:popular:{limit}"

    @staticmethod
    def upcoming_events(limit: int) -> str:
        """Build cache key for upcoming events."""
        return f"events:upcoming:{limit}"

    @staticmethod
    def seat_lock(seat_id: str) -> str:
        """Build cache key for seat selection locks."""
        return f"lock:seat:{seat_id}"

    @staticmethod
    def booking_lock(event_id: str, user_id: str) -> str:
        """Build cache key for booking process locks."""
        return f"lock:booking:{event_id}:{user_id}"


class RedisCache:
    """Redis cache manager with connection handling and operations."""

    def __init__(self):
        self.client: Optional[Redis] = None
        self.pool: Optional[redis.ConnectionPool] = None

    async def initialize(self) -> None:
        """Initialize Redis connection pool and client."""
        settings = get_settings()

        try:
            # Create connection pool
            self.pool = redis.ConnectionPool.from_url(
                settings.redis_url,
                max_connections=settings.redis_max_connections,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )

            # Create Redis client
            self.client = Redis(connection_pool=self.pool)

            # Test connection
            await self.client.ping()
            logger.info("Redis cache initialized successfully")

        except RedisConnectionError as e:
            logger.error("Failed to connect to Redis: %s", e)
            raise
        except Exception as e:
            logger.error("Failed to initialize Redis cache: %s", e)
            raise

    async def close(self) -> None:
        """Close Redis connections."""
        if self.client:
            await self.client.close()
        if self.pool:
            await self.pool.disconnect()
        logger.info("Redis cache connections closed")

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        if not self.client:
            logger.warning("Redis client not initialized")
            return None

        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value.decode('utf-8'))
            return None
        except (RedisError, ValueError) as e:
            logger.warning("Failed to get cache key %s: %s", key, e)
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Redis client not initialized")
            return False

        try:
            serialized_value = json.dumps(value, default=str)
            if ttl:
                await self.client.setex(key, ttl, serialized_value)
            else:
                await self.client.set(key, serialized_value)
            return True
        except (RedisError, TypeError) as e:
            logger.warning("Failed to set cache key %s: %s", key, e)
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Redis client not initialized")
            return False

        try:
            await self.client.delete(key)
            return True
        except RedisError as e:
            logger.warning("Failed to delete cache key %s: %s", key, e)
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.

        Args:
            pattern: Pattern to match (e.g., "events:*")

        Returns:
            Number of keys deleted
        """
        if not self.client:
            logger.warning("Redis client not initialized")
            return 0

        try:
            keys = await self.client.keys(pattern)
            if keys:
                await self.client.delete(*keys)
                return len(keys)
            return 0
        except RedisError as e:
            logger.warning(f"Failed to delete keys with pattern {pattern}: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        if not self.client:
            return False

        try:
            return bool(await self.client.exists(key))
        except RedisError as e:
            logger.warning(f"Failed to check existence of key {key}: {e}")
            return False

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment a numeric value in cache.

        Args:
            key: Cache key
            amount: Amount to increment by

        Returns:
            New value after increment, or None if failed
        """
        if not self.client:
            return None

        try:
            return await self.client.incrby(key, amount)
        except RedisError as e:
            logger.warning(f"Failed to increment key {key}: {e}")
            return None

    async def expire(self, key: str, ttl: int) -> bool:
        """
        Set expiration time for a key.

        Args:
            key: Cache key
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            return False

        try:
            return bool(await self.client.expire(key, ttl))
        except RedisError as e:
            logger.warning(f"Failed to set expiration for key {key}: {e}")
            return False

    # Redis sorted set operations for rate limiting
    async def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        """
        Add members to a sorted set.

        Args:
            key: Sorted set key
            mapping: Dictionary of member -> score pairs

        Returns:
            Number of elements added
        """
        if not self.client:
            return 0

        try:
            return await self.client.zadd(key, mapping)
        except RedisError as e:
            logger.warning(f"Failed to zadd to key {key}: {e}")
            return 0

    async def zcard(self, key: str) -> int:
        """
        Get the number of members in a sorted set.

        Args:
            key: Sorted set key

        Returns:
            Number of members in the sorted set
        """
        if not self.client:
            return 0

        try:
            return await self.client.zcard(key)
        except RedisError as e:
            logger.warning(f"Failed to zcard key {key}: {e}")
            return 0

    async def zrange(self, key: str, start: int, end: int, withscores: bool = False) -> List:
        """
        Get members from a sorted set by index range.

        Args:
            key: Sorted set key
            start: Start index
            end: End index
            withscores: Whether to include scores

        Returns:
            List of members (and scores if withscores=True)
        """
        if not self.client:
            return []

        try:
            return await self.client.zrange(key, start, end, withscores=withscores)
        except RedisError as e:
            logger.warning(f"Failed to zrange key {key}: {e}")
            return []

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        """
        Remove members from a sorted set by score range.

        Args:
            key: Sorted set key
            min_score: Minimum score
            max_score: Maximum score

        Returns:
            Number of members removed
        """
        if not self.client:
            return 0

        try:
            return await self.client.zremrangebyscore(key, min_score, max_score)
        except RedisError as e:
            logger.warning(f"Failed to zremrangebyscore key {key}: {e}")
            return 0

    def pipeline(self):
        """
        Create a Redis pipeline for batch operations.

        Returns:
            Redis pipeline object
        """
        if not self.client:
            return None

        return self.client.pipeline()


class DistributedLock:
    """Distributed lock implementation using Redis."""

    def __init__(self, cache: RedisCache, key: str, timeout: int = 30):
        """
        Initialize distributed lock.

        Args:
            cache: Redis cache instance
            key: Lock key
            timeout: Lock timeout in seconds
        """
        self.cache = cache
        self.key = key
        self.timeout = timeout
        self.identifier = f"{datetime.utcnow().timestamp()}:{id(self)}"

    async def acquire(self, blocking: bool = True, timeout: Optional[int] = None) -> bool:
        """
        Acquire the distributed lock.

        Args:
            blocking: Whether to block until lock is acquired
            timeout: Maximum time to wait for lock (seconds)

        Returns:
            True if lock acquired, False otherwise
        """
        if not self.cache.client:
            return False

        end_time = None
        if timeout:
            end_time = datetime.utcnow() + timedelta(seconds=timeout)

        while True:
            try:
                # Try to acquire lock with SET NX EX
                acquired = await self.cache.client.set(
                    self.key,
                    self.identifier,
                    nx=True,
                    ex=self.timeout
                )

                if acquired:
                    return True

                if not blocking:
                    return False

                if end_time and datetime.utcnow() >= end_time:
                    return False

                # Wait a bit before retrying
                await asyncio.sleep(0.1)

            except RedisError as e:
                logger.warning(f"Failed to acquire lock {self.key}: {e}")
                return False

    async def release(self) -> bool:
        """
        Release the distributed lock.

        Returns:
            True if lock released, False otherwise
        """
        if not self.cache.client:
            return False

        try:
            # Lua script to ensure we only delete our own lock
            lua_script = """
            if redis.call("GET", KEYS[1]) == ARGV[1] then
                return redis.call("DEL", KEYS[1])
            else
                return 0
            end
            """

            result = await self.cache.client.eval(
                lua_script, 1, self.key, self.identifier
            )
            return bool(result)

        except RedisError as e:
            logger.warning(f"Failed to release lock {self.key}: {e}")
            return False

    async def __aenter__(self):
        """Async context manager entry."""
        acquired = await self.acquire()
        if not acquired:
            raise RuntimeError(f"Failed to acquire lock: {self.key}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.release()


# Global cache instance
cache = RedisCache()


async def init_cache() -> None:
    """Initialize the global cache instance."""
    await cache.initialize()


async def close_cache() -> None:
    """Close the global cache instance."""
    await cache.close()


def get_cache() -> RedisCache:
    """Get the global cache instance."""
    return cache


@asynccontextmanager
async def distributed_lock(key: str, timeout: int = 30):
    """
    Context manager for distributed locks.

    Args:
        key: Lock key
        timeout: Lock timeout in seconds

    Usage:
        async with distributed_lock("my_lock_key"):
            # Critical section
            pass
    """
    lock = DistributedLock(cache, key, timeout)
    async with lock:
        yield lock


# Cache invalidation helpers
class CacheInvalidator:
    """Helper class for cache invalidation strategies."""

    @staticmethod
    async def invalidate_event_caches(event_id: str) -> None:
        """Invalidate all caches related to a specific event."""
        patterns = [
            f"event:detail:{event_id}",
            f"seats:map:{event_id}",
            f"seats:availability:{event_id}",
            "events:list:*",
            "events:popular:*",
            "events:upcoming:*"
        ]

        for pattern in patterns:
            if "*" in pattern:
                await cache.delete_pattern(pattern)
            else:
                await cache.delete(pattern)

        logger.info(f"Invalidated caches for event {event_id}")

    @staticmethod
    async def invalidate_seat_caches(event_id: str) -> None:
        """Invalidate seat-related caches for an event."""
        patterns = [
            f"seats:map:{event_id}",
            f"seats:availability:{event_id}"
        ]

        for pattern in patterns:
            await cache.delete(pattern)

        logger.info(f"Invalidated seat caches for event {event_id}")

    @staticmethod
    async def invalidate_event_list_caches() -> None:
        """Invalidate all event listing caches."""
        patterns = [
            "events:list:*",
            "events:popular:*",
            "events:upcoming:*"
        ]

        for pattern in patterns:
            await cache.delete_pattern(pattern)

        logger.info("Invalidated event list caches")


# Cache TTL constants (in seconds)
class CacheTTL:
    """Cache TTL constants for different data types."""

    EVENT_LIST = 300  # 5 minutes
    EVENT_DETAIL = 600  # 10 minutes
    SEAT_MAP = 180  # 3 minutes
    SEAT_AVAILABILITY = 60  # 1 minute
    POPULAR_EVENTS = 900  # 15 minutes
    UPCOMING_EVENTS = 600  # 10 minutes
    LOCK_TIMEOUT = 30  # 30 seconds

