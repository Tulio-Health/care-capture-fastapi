import logging
import json
from enum import StrEnum
from typing import Optional, Dict, Any
import sys
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Log formats
LOG_FORMAT_DEBUG = "%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(pathname)s:%(funcName)s:%(lineno)d"
LOG_FORMAT_DEFAULT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Environment variable names
ENV_LOG_LEVEL = "LOG_LEVEL"
ENV_LOG_FILE = "LOG_FILE"
ENV_ENABLE_CONSOLE_LOG = "ENABLE_CONSOLE_LOG"
ENV_ENABLE_FILE_LOG = "ENABLE_FILE_LOG"
ENV_MAX_LOG_SIZE = "MAX_LOG_SIZE"
ENV_BACKUP_COUNT = "BACKUP_COUNT"
ENV_LOG_FORMAT = "LOG_FORMAT"
ENV_ENABLE_JSON_LOGS = "ENABLE_JSON_LOGS"

# Default values
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_BACKUP_COUNT = 5

class LogLevels(StrEnum):
    """Available log levels for the application"""
    critical = "CRITICAL"
    error = "ERROR"
    warning = "WARNING"
    info = "INFO"
    debug = "DEBUG"


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    
    Outputs logs in JSON format with additional context fields.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON"""
        # Start with basic log data
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "pathname": record.pathname,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add stack info if present
        if record.stack_info:
            log_data["stack_info"] = self.formatStack(record.stack_info)
        
        # Add any extra fields from the log record
        extra_fields = {}
        for key, value in record.__dict__.items():
            # Skip standard logging fields
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
                'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
                'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
                'processName', 'process', 'getMessage', 'message'
            }:
                # Only include serializable values
                try:
                    json.dumps(value)
                    extra_fields[key] = value
                except (TypeError, ValueError):
                    extra_fields[key] = str(value)
        
        if extra_fields:
            log_data["extra"] = extra_fields
        
        try:
            return json.dumps(log_data, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            # Fallback to string representation if JSON serialization fails
            log_data["json_error"] = f"Failed to serialize: {str(e)}"
            return json.dumps({k: str(v) for k, v in log_data.items()}, ensure_ascii=False)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name"""
    return logging.getLogger(name)

def get_log_level() -> str:
    """Get the log level from environment variable"""
    log_level = os.getenv(ENV_LOG_LEVEL, DEFAULT_LOG_LEVEL).upper()
    if log_level not in [level.value for level in LogLevels]:
        return DEFAULT_LOG_LEVEL
    return log_level

def should_enable_console_log() -> bool:
    """Check if console logging should be enabled"""
    return os.getenv(ENV_ENABLE_CONSOLE_LOG, "true").lower() == "true"

def should_enable_file_log() -> bool:
    """Check if file logging should be enabled"""
    return os.getenv(ENV_ENABLE_FILE_LOG, "false").lower() == "true"

def get_log_file() -> Optional[str]:
    """Get the log file path from environment variable"""
    return os.getenv(ENV_LOG_FILE)

def get_max_log_size() -> int:
    """Get the maximum log file size in bytes"""
    try:
        return int(os.getenv(ENV_MAX_LOG_SIZE, DEFAULT_MAX_LOG_SIZE))
    except ValueError:
        return DEFAULT_MAX_LOG_SIZE

def get_backup_count() -> int:
    """Get the number of backup files to keep"""
    try:
        return int(os.getenv(ENV_BACKUP_COUNT, DEFAULT_BACKUP_COUNT))
    except ValueError:
        return DEFAULT_BACKUP_COUNT

def should_enable_json_logs() -> bool:
    """Check if JSON logging should be enabled"""
    return os.getenv(ENV_ENABLE_JSON_LOGS, "false").lower() == "true"

def get_log_format() -> str:
    """Get the preferred log format"""
    return os.getenv(ENV_LOG_FORMAT, "default").lower()

def configure_logging() -> None:
    """
    Configure logging for the application based on environment variables
    """
    log_level = get_log_level()
    handlers = []
    use_json = should_enable_json_logs()
    log_format = get_log_format()
    
    # Determine formatter
    def get_formatter() -> logging.Formatter:
        if use_json or log_format == "json":
            return JSONFormatter()
        elif log_level == LogLevels.debug or log_format == "debug":
            return logging.Formatter(LOG_FORMAT_DEBUG)
        else:
            return logging.Formatter(LOG_FORMAT_DEFAULT)
    
    # Console handler
    if should_enable_console_log():
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(get_formatter())
        handlers.append(console_handler)

    # File handler
    if should_enable_file_log():
        log_file = get_log_file()
        if log_file:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=get_max_log_size(),
                backupCount=get_backup_count()
            )
            file_handler.setFormatter(get_formatter())
            handlers.append(file_handler)

    # Configure logging
    if handlers:
        logging.basicConfig(
            level=log_level,
            handlers=handlers,
            force=True  # Force reconfiguration if already configured
        )
    else:
        logging.basicConfig(level=log_level, force=True) 