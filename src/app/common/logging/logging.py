import logging
from enum import StrEnum
from typing import Optional
import sys
import os
from logging.handlers import RotatingFileHandler

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

def configure_logging() -> None:
    """
    Configure logging for the application based on environment variables
    """
    log_level = get_log_level()
    handlers = []
    
    # Console handler
    if should_enable_console_log():
        console_handler = logging.StreamHandler(sys.stdout)
        if log_level == LogLevels.debug:
            console_handler.setFormatter(logging.Formatter(LOG_FORMAT_DEBUG))
        else:
            console_handler.setFormatter(logging.Formatter(LOG_FORMAT_DEFAULT))
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
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT_DEFAULT))
            handlers.append(file_handler)

    # Configure logging
    if handlers:
        logging.basicConfig(
            level=log_level,
            handlers=handlers
        )
    else:
        logging.basicConfig(level=log_level) 