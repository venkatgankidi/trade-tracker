"""Error handling and logging utilities for the trade tracker application."""

import streamlit as st
import logging
from functools import wraps
from typing import Any, Callable, Optional, TypeVar
import time

# Set up logging
logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])

def handle_database_error(func: F) -> F:
    """Decorator to handle database errors gracefully."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Database error in {func.__name__}: {e}")
            st.error("Database operation failed. Please try again.")
            return None
    return wrapper

def handle_api_error(func: F) -> F:
    """Decorator to handle external API errors gracefully."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"API error in {func.__name__}: {e}")
            st.warning(f"External data unavailable: {str(e)}")
            return None
    return wrapper

def handle_performance_monitor(func: F) -> F:
    """Decorator to monitor function performance."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            if execution_time > 5.0:  # Log slow functions
                logger.warning(f"Slow function {func.__name__}: {execution_time:.2f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Error in {func.__name__} after {execution_time:.2f}s: {e}")
            raise
    return wrapper

class CircuitBreaker:
    """Circuit breaker for external API calls to prevent cascading failures."""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = 'closed'  # closed, open, half_open
    
    def __call__(self, func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if self.state == 'open':
                if time.time() - self.last_failure_time > self.timeout:
                    self.state = 'half_open'
                else:
                    logger.warning(f"Circuit breaker open for {func.__name__}")
                    return None
            
            try:
                result = func(*args, **kwargs)
                if self.state == 'half_open':
                    self.state = 'closed'
                    self.failure_count = 0
                return result
            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = 'open'
                    logger.error(f"Circuit breaker opened for {func.__name__}: {e}")
                
                raise
        
        return wrapper

# Global circuit breaker instances
yfinance_circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=300)
option_chain_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=180)