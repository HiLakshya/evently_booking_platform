"""
Retry mechanisms with exponential backoff for handling transient failures.
"""

import asyncio
import logging
import random
import time
from typing import Any, Callable, Optional, Type, Union, List
from functools import wraps
from dataclasses import dataclass

from ..utils.exceptions import ConcurrencyError, ExternalServiceError

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    backoff_factor: float = 1.0


class RetryableError(Exception):
    """Base class for errors that should trigger retries."""
    pass


class NonRetryableError(Exception):
    """Base class for errors that should not trigger retries."""
    pass


async def retry_async(
    func: Callable,
    config: RetryConfig,
    retryable_exceptions: tuple = (Exception,),
    non_retryable_exceptions: tuple = (),
    *args,
    **kwargs
) -> Any:
    """
    Retry an async function with exponential backoff.
    
    Args:
        func: The async function to retry
        config: Retry configuration
        retryable_exceptions: Exceptions that should trigger retries
        non_retryable_exceptions: Exceptions that should not trigger retries
        *args, **kwargs: Arguments to pass to the function
    
    Returns:
        The result of the function call
    
    Raises:
        The last exception if all retries are exhausted
    """
    last_exception = None
    
    for attempt in range(config.max_attempts):
        try:
            result = await func(*args, **kwargs)
            
            # Log successful retry if this wasn't the first attempt
            if attempt > 0:
                logger.info(f"Function {func.__name__} succeeded on attempt {attempt + 1}")
            
            return result
            
        except non_retryable_exceptions as e:
            logger.error(f"Non-retryable error in {func.__name__}: {e}")
            raise
            
        except retryable_exceptions as e:
            last_exception = e
            
            # Don't sleep after the last attempt
            if attempt == config.max_attempts - 1:
                break
            
            # Calculate delay with exponential backoff
            delay = min(
                config.base_delay * (config.exponential_base ** attempt) * config.backoff_factor,
                config.max_delay
            )
            
            # Add jitter to prevent thundering herd
            if config.jitter:
                delay = delay * (0.5 + random.random() * 0.5)
            
            logger.warning(
                f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                f"Retrying in {delay:.2f}s..."
            )
            
            await asyncio.sleep(delay)
    
    # All retries exhausted
    logger.error(f"All {config.max_attempts} attempts failed for {func.__name__}")
    raise last_exception


def retry_on_concurrency_error(
    max_attempts: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    jitter: bool = True
):
    """Decorator for retrying operations that may fail due to concurrency issues."""
    
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        jitter=jitter
    )
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(
                func,
                config,
                retryable_exceptions=(ConcurrencyError, asyncio.TimeoutError),
                non_retryable_exceptions=(ValueError, TypeError),
                *args,
                **kwargs
            )
        return wrapper
    
    return decorator


def retry_on_external_service_error(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0
):
    """Decorator for retrying external service calls."""
    
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=2.0,
        jitter=True
    )
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(
                func,
                config,
                retryable_exceptions=(ExternalServiceError, asyncio.TimeoutError, ConnectionError),
                non_retryable_exceptions=(ValueError, TypeError, KeyError),
                *args,
                **kwargs
            )
        return wrapper
    
    return decorator


class RetryableOperation:
    """Context manager for retryable operations with detailed logging."""
    
    def __init__(
        self,
        operation_name: str,
        config: RetryConfig,
        retryable_exceptions: tuple = (Exception,),
        non_retryable_exceptions: tuple = ()
    ):
        self.operation_name = operation_name
        self.config = config
        self.retryable_exceptions = retryable_exceptions
        self.non_retryable_exceptions = non_retryable_exceptions
        self.attempt = 0
        self.start_time = None
        self.total_delay = 0.0
    
    async def __aenter__(self):
        self.start_time = time.time()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            # Success
            total_time = time.time() - self.start_time
            if self.attempt > 0:
                logger.info(
                    f"Operation '{self.operation_name}' succeeded after {self.attempt + 1} attempts "
                    f"in {total_time:.2f}s (including {self.total_delay:.2f}s retry delays)"
                )
            return True
        
        # Handle exceptions
        if issubclass(exc_type, self.non_retryable_exceptions):
            logger.error(f"Non-retryable error in '{self.operation_name}': {exc_val}")
            return False
        
        if not issubclass(exc_type, self.retryable_exceptions):
            logger.error(f"Unexpected error in '{self.operation_name}': {exc_val}")
            return False
        
        # Check if we should retry
        if self.attempt >= self.config.max_attempts - 1:
            total_time = time.time() - self.start_time
            logger.error(
                f"Operation '{self.operation_name}' failed after {self.attempt + 1} attempts "
                f"in {total_time:.2f}s. Last error: {exc_val}"
            )
            return False
        
        # Calculate delay and retry
        delay = min(
            self.config.base_delay * (self.config.exponential_base ** self.attempt) * self.config.backoff_factor,
            self.config.max_delay
        )
        
        if self.config.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        
        self.total_delay += delay
        
        logger.warning(
            f"Attempt {self.attempt + 1} failed for '{self.operation_name}': {exc_val}. "
            f"Retrying in {delay:.2f}s..."
        )
        
        await asyncio.sleep(delay)
        self.attempt += 1
        
        # Suppress the exception to retry
        return True


async def retry_with_circuit_breaker(
    func: Callable,
    circuit_breaker,
    retry_config: RetryConfig,
    *args,
    **kwargs
) -> Any:
    """Combine retry logic with circuit breaker pattern."""
    
    async def wrapped_func():
        return await circuit_breaker.call(func, *args, **kwargs)
    
    return await retry_async(
        wrapped_func,
        retry_config,
        retryable_exceptions=(ConcurrencyError, ExternalServiceError),
        non_retryable_exceptions=(ValueError, TypeError)
    )


class BulkRetryManager:
    """Manager for handling bulk operations with individual retry logic."""
    
    def __init__(self, config: RetryConfig):
        self.config = config
        self.results = []
        self.failures = []
    
    async def execute_bulk(
        self,
        operations: List[Callable],
        fail_fast: bool = False,
        max_concurrent: int = 10
    ) -> tuple:
        """
        Execute multiple operations with retry logic.
        
        Args:
            operations: List of async functions to execute
            fail_fast: If True, stop on first permanent failure
            max_concurrent: Maximum concurrent operations
        
        Returns:
            Tuple of (successful_results, failed_operations)
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def execute_with_retry(operation, index):
            async with semaphore:
                try:
                    result = await retry_async(
                        operation,
                        self.config,
                        retryable_exceptions=(ConcurrencyError, ExternalServiceError, asyncio.TimeoutError),
                        non_retryable_exceptions=(ValueError, TypeError)
                    )
                    return {"index": index, "result": result, "success": True}
                except Exception as e:
                    return {"index": index, "error": e, "success": False}
        
        # Execute all operations concurrently
        tasks = [
            execute_with_retry(op, i) 
            for i, op in enumerate(operations)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_results = []
        failed_operations = []
        
        for result in results:
            if isinstance(result, Exception):
                failed_operations.append(result)
                if fail_fast:
                    break
            elif result["success"]:
                successful_results.append(result)
            else:
                failed_operations.append(result)
                if fail_fast:
                    break
        
        return successful_results, failed_operations