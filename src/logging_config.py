"""
Centralized logging configuration for the medical warehouse project.
Provides structured logging with JSON output and file rotation.
"""

import logging
import logging.handlers
import json
import os
from datetime import datetime
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def setup_logger(name, log_level=logging.INFO, log_dir='logs'):
    """
    Set up a logger with both file and console handlers.
    
    Args:
        name: Logger name (typically __name__)
        log_level: Logging level (default: INFO)
        log_dir: Directory for log files
    
    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    # Console Handler (human-readable)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # File Handler (JSON format, rotated)
    log_filename = os.path.join(log_dir, f'{name.replace(".", "_")}.log')
    file_handler = logging.handlers.RotatingFileHandler(
        log_filename,
        maxBytes=10_000_000,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


# Application loggers
logger_scraper = setup_logger('medical_warehouse.scraper')
logger_loader = setup_logger('medical_warehouse.loader')
logger_transformer = setup_logger('medical_warehouse.transformer')
logger_api = setup_logger('medical_warehouse.api')