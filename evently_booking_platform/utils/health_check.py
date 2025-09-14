"""
Health check utilities for monitoring service dependencies.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..cache import get_cache
from ..config import get_settings

logger = logging.getLogger(__name__)


class HealthCheckResult:
    """Result of a health check."""
    
    def __init__(self, service: str, healthy: bool, response_time: float, details: Dict[str, Any] = None):
        self.service = service
        self.healthy = healthy
        self.response_time = response_time
        self.details = details or {}
        self.timestamp = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "service": self.service,
            "healthy": self.healthy,
            "response_time": self.response_time,
            "details": self.details,
            "timestamp": self.timestamp
        }


async def check_database_health() -> HealthCheckResult:
    """Check database connectivity and performance."""
    start_time = time.time()
    
    try:
        # Get database session
        async for db in get_db():
            # Simple query to test connectivity
            result = await db.execute(text("SELECT 1 as health_check"))
            row = result.fetchone()
            
            if row and row[0] == 1:
                response_time = time.time() - start_time
                return HealthCheckResult(
                    service="database",
                    healthy=True,
                    response_time=response_time,
                    details={"query": "SELECT 1", "result": "success"}
                )
            else:
                response_time = time.time() - start_time
                return HealthCheckResult(
                    service="database",
                    healthy=False,
                    response_time=response_time,
                    details={"error": "Unexpected query result"}
                )
    
    except Exception as e:
        response_time = time.time() - start_time
        logger.error(f"Database health check failed: {e}")
        return HealthCheckResult(
            service="database",
            healthy=False,
            response_time=response_time,
            details={"error": str(e), "error_type": type(e).__name__}
        )


async def check_redis_health() -> HealthCheckResult:
    """Check Redis connectivity and performance."""
    start_time = time.time()
    
    try:
        cache = get_cache()
        
        # Test basic operations
        test_key = "health_check:test"
        test_value = "health_check_value"
        
        # Set a test value
        await cache.set(test_key, test_value, ex=10)
        
        # Get the test value
        retrieved_value = await cache.get(test_key)
        
        # Clean up
        await cache.delete(test_key)
        
        response_time = time.time() - start_time
        
        if retrieved_value == test_value:
            return HealthCheckResult(
                service="redis",
                healthy=True,
                response_time=response_time,
                details={"operations": ["set", "get", "delete"], "result": "success"}
            )
        else:
            return HealthCheckResult(
                service="redis",
                healthy=False,
                response_time=response_time,
                details={"error": "Value mismatch in Redis operations"}
            )
    
    except Exception as e:
        response_time = time.time() - start_time
        logger.error(f"Redis health check failed: {e}")
        return HealthCheckResult(
            service="redis",
            healthy=False,
            response_time=response_time,
            details={"error": str(e), "error_type": type(e).__name__}
        )


async def check_celery_health() -> HealthCheckResult:
    """Check Celery worker connectivity."""
    start_time = time.time()
    
    try:
        from ..tasks.celery_app import celery_app
        
        # Check if workers are available
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        
        response_time = time.time() - start_time
        
        if stats:
            active_workers = len(stats)
            return HealthCheckResult(
                service="celery",
                healthy=True,
                response_time=response_time,
                details={"active_workers": active_workers, "workers": list(stats.keys())}
            )
        else:
            return HealthCheckResult(
                service="celery",
                healthy=False,
                response_time=response_time,
                details={"error": "No active Celery workers found"}
            )
    
    except Exception as e:
        response_time = time.time() - start_time
        logger.error(f"Celery health check failed: {e}")
        return HealthCheckResult(
            service="celery",
            healthy=False,
            response_time=response_time,
            details={"error": str(e), "error_type": type(e).__name__}
        )


async def check_external_services_health() -> List[HealthCheckResult]:
    """Check external service dependencies."""
    results = []
    settings = get_settings()
    
    # Check email service if configured
    if settings.smtp_server:
        result = await check_smtp_health()
        results.append(result)
    
    return results


async def check_smtp_health() -> HealthCheckResult:
    """Check SMTP server connectivity."""
    start_time = time.time()
    settings = get_settings()
    
    try:
        import smtplib
        import ssl
        
        # Create SMTP connection
        if settings.smtp_use_tls:
            context = ssl.create_default_context()
            server = smtplib.SMTP(settings.smtp_server, settings.smtp_port)
            server.starttls(context=context)
        else:
            server = smtplib.SMTP(settings.smtp_server, settings.smtp_port)
        
        # Authenticate if credentials provided
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        
        # Close connection
        server.quit()
        
        response_time = time.time() - start_time
        return HealthCheckResult(
            service="smtp",
            healthy=True,
            response_time=response_time,
            details={"server": settings.smtp_server, "port": settings.smtp_port}
        )
    
    except Exception as e:
        response_time = time.time() - start_time
        logger.error(f"SMTP health check failed: {e}")
        return HealthCheckResult(
            service="smtp",
            healthy=False,
            response_time=response_time,
            details={"error": str(e), "error_type": type(e).__name__}
        )


async def get_health_status() -> Dict[str, Any]:
    """Get comprehensive health status of all services."""
    start_time = time.time()
    
    # Run all health checks concurrently
    health_checks = await asyncio.gather(
        check_database_health(),
        check_redis_health(),
        check_celery_health(),
        return_exceptions=True
    )
    
    # Add external service checks
    external_checks = await check_external_services_health()
    health_checks.extend(external_checks)
    
    # Process results
    results = []
    overall_healthy = True
    
    for check in health_checks:
        if isinstance(check, Exception):
            logger.error(f"Health check failed with exception: {check}")
            results.append(HealthCheckResult(
                service="unknown",
                healthy=False,
                response_time=0.0,
                details={"error": str(check)}
            ).to_dict())
            overall_healthy = False
        else:
            results.append(check.to_dict())
            if not check.healthy:
                overall_healthy = False
    
    total_time = time.time() - start_time
    
    return {
        "status": "healthy" if overall_healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_check_time": total_time,
        "services": results,
        "summary": {
            "total_services": len(results),
            "healthy_services": sum(1 for r in results if r["healthy"]),
            "unhealthy_services": sum(1 for r in results if not r["healthy"])
        }
    }


async def get_readiness_status() -> Dict[str, Any]:
    """Get readiness status (can the service handle requests?)."""
    # Check critical services only
    critical_checks = await asyncio.gather(
        check_database_health(),
        check_redis_health(),
        return_exceptions=True
    )
    
    ready = True
    for check in critical_checks:
        if isinstance(check, Exception) or not check.healthy:
            ready = False
            break
    
    return {
        "ready": ready,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


async def get_liveness_status() -> Dict[str, Any]:
    """Get liveness status (is the service running?)."""
    # Simple check that the service is responsive
    return {
        "alive": True,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "uptime": time.time()  # This would be actual uptime in production
    }