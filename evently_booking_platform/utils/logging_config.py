"""
Comprehensive logging configuration for the Evently Booking Platform.
"""

import logging
import logging.config
import sys
from typing import Dict, Any, Optional
from pathlib import Path

from ..config import get_settings


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_json_logging: bool = False,
    enable_structured_logging: bool = True
) -> None:
    """
    Set up comprehensive logging configuration.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
        enable_json_logging: Enable JSON formatted logs
        enable_structured_logging: Enable structured logging with extra fields
    """
    settings = get_settings()
    
    # Create logs directory if logging to file
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Base logging configuration
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "detailed": {
                "format": (
                    "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d "
                    "[%(request_id)s] %(message)s"
                ),
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "json": {
                "()": "evently_booking_platform.utils.logging_config.JSONFormatter",
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s"
            }
        },
        "filters": {
            "request_id": {
                "()": "evently_booking_platform.utils.logging_config.RequestIDFilter"
            },
            "sensitive_data": {
                "()": "evently_booking_platform.utils.logging_config.SensitiveDataFilter"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "json" if enable_json_logging else "detailed",
                "stream": sys.stdout,
                "filters": ["request_id", "sensitive_data"]
            }
        },
        "loggers": {
            # Application loggers
            "evently_booking_platform": {
                "level": log_level,
                "handlers": ["console"],
                "propagate": False
            },
            
            # FastAPI and Uvicorn
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False
            },
            "fastapi": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False
            },
            
            # Database
            "sqlalchemy.engine": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False
            },
            "sqlalchemy.pool": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False
            },
            
            # Redis
            "redis": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False
            },
            
            # Celery
            "celery": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False
            },
            
            # Third-party libraries
            "httpx": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False
            },
            "urllib3": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False
            }
        },
        "root": {
            "level": log_level,
            "handlers": ["console"]
        }
    }
    
    # Add file handler if specified
    if log_file:
        config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": log_level,
            "formatter": "json" if enable_json_logging else "detailed",
            "filename": log_file,
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 5,
            "filters": ["request_id", "sensitive_data"]
        }
        
        # Add file handler to all loggers
        for logger_config in config["loggers"].values():
            if "file" not in logger_config["handlers"]:
                logger_config["handlers"].append("file")
        
        config["root"]["handlers"].append("file")
    
    # Add error file handler for production
    if settings.environment == "production":
        error_file = log_file.replace(".log", "_errors.log") if log_file else "logs/errors.log"
        
        config["handlers"]["error_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "formatter": "json" if enable_json_logging else "detailed",
            "filename": error_file,
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 10,
            "filters": ["request_id", "sensitive_data"]
        }
        
        # Add error handler to application loggers
        config["loggers"]["evently_booking_platform"]["handlers"].append("error_file")
    
    # Apply configuration
    logging.config.dictConfig(config)
    
    # Set up exception logging
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        logger = logging.getLogger("evently_booking_platform.exceptions")
        logger.error(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback),
            extra={"exception_type": exc_type.__name__}
        )
    
    sys.excepthook = handle_exception


class RequestIDFilter(logging.Filter):
    """Filter to add request ID to log records."""
    
    def filter(self, record):
        # Try to get request ID from various sources
        request_id = getattr(record, 'request_id', None)
        
        if not request_id:
            # Try to get from context variables
            try:
                from evently_booking_platform.middleware.logging import request_id_var
                request_id = request_id_var.get()
            except (ImportError, LookupError):
                request_id = 'no-request-id'
        
        record.request_id = request_id
        return True


class SensitiveDataFilter(logging.Filter):
    """Filter to remove sensitive data from log records."""
    
    SENSITIVE_KEYS = {
        'password', 'token', 'secret', 'key', 'authorization',
        'cookie', 'session', 'csrf', 'api_key', 'access_token',
        'refresh_token', 'private_key', 'credit_card', 'ssn'
    }
    
    def filter(self, record):
        # Sanitize the message
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = self._sanitize_string(record.msg)
        
        # Sanitize extra fields
        if hasattr(record, '__dict__'):
            for key, value in record.__dict__.items():
                if isinstance(value, (str, dict)):
                    setattr(record, key, self._sanitize_data(value))
        
        return True
    
    def _sanitize_string(self, text: str) -> str:
        """Sanitize sensitive data in strings."""
        # Simple pattern matching for common sensitive data
        import re
        
        # Mask potential tokens/keys
        text = re.sub(r'\b[A-Za-z0-9]{32,}\b', '***MASKED***', text)
        
        # Mask email addresses in some contexts
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***EMAIL***', text)
        
        return text
    
    def _sanitize_data(self, data):
        """Recursively sanitize sensitive data."""
        if isinstance(data, dict):
            return {
                key: '***MASKED***' if any(sensitive in key.lower() for sensitive in self.SENSITIVE_KEYS)
                else self._sanitize_data(value)
                for key, value in data.items()
            }
        elif isinstance(data, str):
            return self._sanitize_string(data)
        elif isinstance(data, (list, tuple)):
            return type(data)(self._sanitize_data(item) for item in data)
        else:
            return data


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record):
        import json
        from datetime import datetime
        
        # Create log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add request ID if available
        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                'filename', 'module', 'lineno', 'funcName', 'created',
                'msecs', 'relativeCreated', 'thread', 'threadName',
                'processName', 'process', 'getMessage', 'exc_info',
                'exc_text', 'stack_info', 'request_id'
            }:
                extra_fields[key] = value
        
        if extra_fields:
            log_entry["extra"] = extra_fields
        
        return json.dumps(log_entry, default=str, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name."""
    return logging.getLogger(name)


def log_performance(operation_name: str, duration: float, **kwargs):
    """Log performance metrics."""
    logger = get_logger("evently_booking_platform.performance")
    logger.info(
        f"Performance: {operation_name} completed in {duration:.4f}s",
        extra={
            "operation": operation_name,
            "duration": duration,
            "performance_metric": True,
            **kwargs
        }
    )


def log_business_event(event_type: str, details: Dict[str, Any], user_id: Optional[str] = None):
    """Log business events for analytics."""
    logger = get_logger("evently_booking_platform.business")
    logger.info(
        f"Business event: {event_type}",
        extra={
            "event_type": event_type,
            "business_event": True,
            "user_id": user_id,
            **details
        }
    )


def log_security_event(event_type: str, details: Dict[str, Any], severity: str = "WARNING"):
    """Log security-related events."""
    logger = get_logger("evently_booking_platform.security")
    
    log_method = getattr(logger, severity.lower(), logger.warning)
    log_method(
        f"Security event: {event_type}",
        extra={
            "event_type": event_type,
            "security_event": True,
            "severity": severity,
            **details
        }
    )