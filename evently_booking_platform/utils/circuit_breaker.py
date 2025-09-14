"""
Circuit breaker pattern implementation for external service calls.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional, Union
from dataclasses import dataclass, field
from functools import wraps

from ..utils.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, failing fast
    HALF_OPEN = "half_open"  # Testing if service is back


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5          # Number of failures to open circuit
    recovery_timeout: int = 60          # Seconds to wait before trying again
    expected_exception: type = Exception  # Exception type that counts as failure
    success_threshold: int = 3          # Successes needed to close circuit in half-open state
    timeout: float = 30.0               # Request timeout in seconds


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0
    state_changes: Dict[str, int] = field(default_factory=lambda: {
        "closed_to_open": 0,
        "open_to_half_open": 0,
        "half_open_to_closed": 0,
        "half_open_to_open": 0
    })


class CircuitBreaker:
    """Circuit breaker implementation for external service calls."""
    
    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            self.stats.total_requests += 1
            
            # Check if circuit should be opened
            if self._should_open_circuit():
                await self._open_circuit()
            
            # Check if circuit should transition to half-open
            if self._should_attempt_reset():
                await self._half_open_circuit()
            
            # If circuit is open, fail fast
            if self.stats.state == CircuitState.OPEN:
                raise ExternalServiceError(
                    self.name,
                    f"Circuit breaker is OPEN for {self.name}",
                    details={
                        "state": self.stats.state.value,
                        "failure_count": self.stats.failure_count,
                        "last_failure_time": self.stats.last_failure_time
                    }
                )
        
        # Execute the function
        try:
            # Apply timeout
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.timeout
            )
            
            await self._record_success()
            return result
            
        except asyncio.TimeoutError:
            await self._record_failure()
            raise ExternalServiceError(
                self.name,
                f"Request timeout after {self.config.timeout}s",
                details={"timeout": self.config.timeout}
            )
        except self.config.expected_exception as e:
            await self._record_failure()
            raise ExternalServiceError(
                self.name,
                f"Service call failed: {str(e)}",
                details={"original_error": str(e)}
            )
        except Exception as e:
            # Unexpected exceptions don't count as failures
            logger.error(f"Unexpected error in circuit breaker {self.name}: {e}")
            raise
    
    async def _record_success(self):
        """Record a successful call."""
        async with self._lock:
            self.stats.success_count += 1
            self.stats.total_successes += 1
            self.stats.last_success_time = time.time()
            
            # Reset failure count on success
            if self.stats.state == CircuitState.CLOSED:
                self.stats.failure_count = 0
            
            # Check if we should close the circuit from half-open
            if (self.stats.state == CircuitState.HALF_OPEN and 
                self.stats.success_count >= self.config.success_threshold):
                await self._close_circuit()
            
            logger.debug(f"Circuit breaker {self.name}: Success recorded")
    
    async def _record_failure(self):
        """Record a failed call."""
        async with self._lock:
            self.stats.failure_count += 1
            self.stats.total_failures += 1
            self.stats.last_failure_time = time.time()
            
            # Reset success count on failure
            if self.stats.state == CircuitState.HALF_OPEN:
                self.stats.success_count = 0
                await self._open_circuit()
            
            logger.warning(f"Circuit breaker {self.name}: Failure recorded ({self.stats.failure_count})")
    
    def _should_open_circuit(self) -> bool:
        """Check if circuit should be opened."""
        return (self.stats.state == CircuitState.CLOSED and 
                self.stats.failure_count >= self.config.failure_threshold)
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt to reset to half-open."""
        if self.stats.state != CircuitState.OPEN:
            return False
        
        if not self.stats.last_failure_time:
            return False
        
        time_since_failure = time.time() - self.stats.last_failure_time
        return time_since_failure >= self.config.recovery_timeout
    
    async def _open_circuit(self):
        """Open the circuit."""
        old_state = self.stats.state
        self.stats.state = CircuitState.OPEN
        
        if old_state == CircuitState.CLOSED:
            self.stats.state_changes["closed_to_open"] += 1
        elif old_state == CircuitState.HALF_OPEN:
            self.stats.state_changes["half_open_to_open"] += 1
        
        logger.warning(f"Circuit breaker {self.name}: OPENED (failures: {self.stats.failure_count})")
    
    async def _half_open_circuit(self):
        """Transition circuit to half-open state."""
        self.stats.state = CircuitState.HALF_OPEN
        self.stats.success_count = 0
        self.stats.state_changes["open_to_half_open"] += 1
        
        logger.info(f"Circuit breaker {self.name}: HALF-OPEN (attempting recovery)")
    
    async def _close_circuit(self):
        """Close the circuit."""
        self.stats.state = CircuitState.CLOSED
        self.stats.failure_count = 0
        self.stats.success_count = 0
        self.stats.state_changes["half_open_to_closed"] += 1
        
        logger.info(f"Circuit breaker {self.name}: CLOSED (service recovered)")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.stats.state.value,
            "failure_count": self.stats.failure_count,
            "success_count": self.stats.success_count,
            "total_requests": self.stats.total_requests,
            "total_failures": self.stats.total_failures,
            "total_successes": self.stats.total_successes,
            "success_rate": (
                self.stats.total_successes / self.stats.total_requests 
                if self.stats.total_requests > 0 else 0
            ),
            "last_failure_time": self.stats.last_failure_time,
            "last_success_time": self.stats.last_success_time,
            "state_changes": self.stats.state_changes.copy(),
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "success_threshold": self.config.success_threshold,
                "timeout": self.config.timeout
            }
        }


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""
    
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
    
    def get_breaker(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get or create a circuit breaker."""
        if name not in self._breakers:
            if config is None:
                config = CircuitBreakerConfig()
            self._breakers[name] = CircuitBreaker(name, config)
        
        return self._breakers[name]
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        return {name: breaker.get_stats() for name, breaker in self._breakers.items()}
    
    def reset_breaker(self, name: str):
        """Reset a specific circuit breaker."""
        if name in self._breakers:
            breaker = self._breakers[name]
            breaker.stats = CircuitBreakerStats()
            logger.info(f"Circuit breaker {name} has been reset")


# Global registry instance
_registry = CircuitBreakerRegistry()


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Get a circuit breaker from the global registry."""
    return _registry.get_breaker(name, config)


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: type = Exception,
    success_threshold: int = 3,
    timeout: float = 30.0
):
    """Decorator for applying circuit breaker to async functions."""
    
    config = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        expected_exception=expected_exception,
        success_threshold=success_threshold,
        timeout=timeout
    )
    
    breaker = get_circuit_breaker(name, config)
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)
        return wrapper
    
    return decorator


# Predefined circuit breakers for common services
def get_email_circuit_breaker() -> CircuitBreaker:
    """Get circuit breaker for email service."""
    config = CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=300,  # 5 minutes
        timeout=10.0
    )
    return get_circuit_breaker("email_service", config)


def get_payment_circuit_breaker() -> CircuitBreaker:
    """Get circuit breaker for payment service."""
    config = CircuitBreakerConfig(
        failure_threshold=2,
        recovery_timeout=120,  # 2 minutes
        timeout=15.0
    )
    return get_circuit_breaker("payment_service", config)


def get_cache_circuit_breaker() -> CircuitBreaker:
    """Get circuit breaker for cache service."""
    config = CircuitBreakerConfig(
        failure_threshold=5,
        recovery_timeout=30,  # 30 seconds
        timeout=5.0
    )
    return get_circuit_breaker("cache_service", config)