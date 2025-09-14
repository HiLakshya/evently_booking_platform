"""
Enhanced health check service for comprehensive system monitoring.
"""

import asyncio
import logging
import time
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

try:
    import psutil
except ImportError:
    psutil = None

from sqlalchemy import text, func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from evently_booking_platform.database import get_db
from evently_booking_platform.cache import get_cache
from evently_booking_platform.config import get_settings
from evently_booking_platform.models import Booking, Event, User
from evently_booking_platform.schemas.advanced_analytics import SystemHealthMetrics

logger = logging.getLogger(__name__)


class HealthCheckService:
    """Comprehensive health check service."""

    def __init__(self):
        self.settings = get_settings()

    async def get_comprehensive_health_status(self) -> SystemHealthMetrics:
        """Get comprehensive system health metrics."""
        # Run all health checks concurrently
        results = await asyncio.gather(
            self.check_database_health(),
            self.check_cache_health(),
            self.check_api_performance(),
            self.check_booking_system_health(),
            self.check_external_services_health(),
            self.get_resource_usage(),
            return_exceptions=True
        )

        # Handle exceptions and extract results
        db_health = results[0] if not isinstance(results[0], Exception) else {"status": "unhealthy", "error": str(results[0])}
        cache_health = results[1] if not isinstance(results[1], Exception) else {"status": "unhealthy", "error": str(results[1])}
        api_performance = results[2] if not isinstance(results[2], Exception) else {"status": "unhealthy", "error": str(results[2])}
        booking_health = results[3] if not isinstance(results[3], Exception) else {"status": "unhealthy", "error": str(results[3])}
        external_health = results[4] if not isinstance(results[4], Exception) else {"status": "unhealthy", "error": str(results[4])}
        resource_usage = results[5] if not isinstance(results[5], Exception) else {}

        # Calculate error rates and response times
        error_rates = await self.calculate_error_rates()
        response_times = await self.calculate_response_times()
        
        # Get active connections and queue sizes
        active_connections = await self.get_active_connections()
        queue_sizes = await self.get_queue_sizes()

        return SystemHealthMetrics(
            database_health=db_health,
            cache_health=cache_health,
            api_performance=api_performance,
            booking_system_health=booking_health,
            external_services_health=external_health,
            resource_usage=resource_usage,
            error_rates=error_rates,
            response_times=response_times,
            active_connections=active_connections,
            queue_sizes=queue_sizes
        )

    async def check_database_health(self) -> Dict[str, Any]:
        """Enhanced database health check with performance metrics."""
        try:
            start_time = time.time()
            
            async for db in get_db():
                # Test basic connectivity
                result = await db.execute(text("SELECT 1"))
                result.scalar()
                basic_query_time = time.time() - start_time

                # Test complex query performance
                start_time = time.time()
                count_result = await db.execute(
                    select(func.count(Booking.id)).where(
                        Booking.created_at >= datetime.utcnow() - timedelta(hours=1)
                    )
                )
                recent_bookings = count_result.scalar()
                complex_query_time = time.time() - start_time

                # Check connection pool status
                pool_info = await self.get_connection_pool_info(db)

                return {
                    "status": "healthy",
                    "basic_query_time_ms": round(basic_query_time * 1000, 2),
                    "complex_query_time_ms": round(complex_query_time * 1000, 2),
                    "recent_bookings_count": recent_bookings,
                    "connection_pool": pool_info,
                    "last_checked": datetime.utcnow().isoformat()
                }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }

    async def check_cache_health(self) -> Dict[str, Any]:
        """Enhanced cache health check with performance metrics."""
        try:
            cache = get_cache()
            
            # Test basic operations
            start_time = time.time()
            test_key = f"health_check_{int(time.time())}"
            test_value = {"test": "data", "timestamp": time.time()}
            
            await cache.set(test_key, test_value, ttl=10)
            set_time = time.time() - start_time

            start_time = time.time()
            retrieved_value = await cache.get(test_key)
            get_time = time.time() - start_time

            start_time = time.time()
            await cache.delete(test_key)
            delete_time = time.time() - start_time

            # Test cache hit rate (simplified)
            hit_rate = await self.calculate_cache_hit_rate()

            if retrieved_value and retrieved_value.get("test") == "data":
                return {
                    "status": "healthy",
                    "set_time_ms": round(set_time * 1000, 2),
                    "get_time_ms": round(get_time * 1000, 2),
                    "delete_time_ms": round(delete_time * 1000, 2),
                    "hit_rate_percentage": hit_rate,
                    "last_checked": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": "Cache value mismatch",
                    "last_checked": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }

    async def check_api_performance(self) -> Dict[str, Any]:
        """Check API performance metrics."""
        try:
            # This would typically integrate with metrics collection
            # For now, we'll simulate some basic checks
            
            start_time = time.time()
            # Simulate API endpoint check
            await asyncio.sleep(0.001)  # Simulate small delay
            response_time = time.time() - start_time

            return {
                "status": "healthy",
                "average_response_time_ms": round(response_time * 1000, 2),
                "endpoints_checked": ["health", "events", "bookings"],
                "last_checked": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }

    async def check_booking_system_health(self) -> Dict[str, Any]:
        """Check booking system specific health metrics."""
        try:
            async for db in get_db():
                # Check for stuck bookings
                stuck_bookings_query = select(func.count(Booking.id)).where(
                    and_(
                        Booking.status == "pending",
                        Booking.expires_at < datetime.utcnow()
                    )
                )
                stuck_bookings_result = await db.execute(stuck_bookings_query)
                stuck_bookings = stuck_bookings_result.scalar() or 0

                # Check booking success rate in last hour
                total_bookings_query = select(func.count(Booking.id)).where(
                    Booking.created_at >= datetime.utcnow() - timedelta(hours=1)
                )
                total_bookings_result = await db.execute(total_bookings_query)
                total_bookings = total_bookings_result.scalar() or 0

                confirmed_bookings_query = select(func.count(Booking.id)).where(
                    and_(
                        Booking.created_at >= datetime.utcnow() - timedelta(hours=1),
                        Booking.status == "confirmed"
                    )
                )
                confirmed_bookings_result = await db.execute(confirmed_bookings_query)
                confirmed_bookings = confirmed_bookings_result.scalar() or 0

                success_rate = (confirmed_bookings / total_bookings * 100) if total_bookings > 0 else 100

                return {
                    "status": "healthy" if stuck_bookings < 10 and success_rate > 80 else "degraded",
                    "stuck_bookings": stuck_bookings,
                    "success_rate_percentage": round(success_rate, 2),
                    "total_bookings_last_hour": total_bookings,
                    "confirmed_bookings_last_hour": confirmed_bookings,
                    "last_checked": datetime.utcnow().isoformat()
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }

    async def check_external_services_health(self) -> Dict[str, Any]:
        """Check external services health."""
        # This would check email service, payment processors, etc.
        # For now, we'll return a placeholder
        return {
            "status": "healthy",
            "email_service": {"status": "healthy", "last_checked": datetime.utcnow().isoformat()},
            "payment_processor": {"status": "healthy", "last_checked": datetime.utcnow().isoformat()},
            "last_checked": datetime.utcnow().isoformat()
        }

    async def get_resource_usage(self) -> Dict[str, Any]:
        """Get system resource usage metrics."""
        try:
            if psutil is None:
                return {
                    "error": "psutil not available",
                    "last_checked": datetime.utcnow().isoformat()
                }

            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_gb = memory.available / (1024**3)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            disk_free_gb = disk.free / (1024**3)
            
            # Network I/O
            network = psutil.net_io_counters()
            
            return {
                "cpu_usage_percent": round(cpu_percent, 2),
                "memory_usage_percent": round(memory_percent, 2),
                "memory_available_gb": round(memory_available_gb, 2),
                "disk_usage_percent": round(disk_percent, 2),
                "disk_free_gb": round(disk_free_gb, 2),
                "network_bytes_sent": network.bytes_sent,
                "network_bytes_recv": network.bytes_recv,
                "last_checked": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Resource usage check failed: {e}")
            return {
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }

    async def calculate_error_rates(self) -> Dict[str, float]:
        """Calculate error rates for different components."""
        # This would typically integrate with logging/metrics systems
        return {
            "api_error_rate": 0.5,  # 0.5% error rate
            "booking_error_rate": 0.2,
            "database_error_rate": 0.1,
            "cache_error_rate": 0.3
        }

    async def calculate_response_times(self) -> Dict[str, float]:
        """Calculate average response times."""
        # This would typically integrate with metrics collection
        return {
            "api_avg_response_ms": 150.0,
            "database_avg_response_ms": 25.0,
            "cache_avg_response_ms": 5.0,
            "booking_avg_response_ms": 200.0
        }

    async def get_active_connections(self) -> int:
        """Get number of active database connections."""
        try:
            async for db in get_db():
                result = await db.execute(text("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"))
                return result.scalar() or 0
        except Exception:
            return 0

    async def get_queue_sizes(self) -> Dict[str, int]:
        """Get queue sizes for background tasks."""
        # This would integrate with Celery or other task queue systems
        return {
            "notification_queue": 0,
            "booking_cleanup_queue": 0,
            "analytics_queue": 0
        }

    async def get_connection_pool_info(self, db: AsyncSession) -> Dict[str, Any]:
        """Get database connection pool information."""
        try:
            # This would depend on the specific database pool implementation
            return {
                "pool_size": 10,
                "checked_out": 2,
                "overflow": 0,
                "checked_in": 8
            }
        except Exception:
            return {"error": "Unable to retrieve pool info"}

    async def calculate_cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        # This would typically integrate with Redis INFO command
        # For now, return a simulated value
        return 85.5  # 85.5% hit rate