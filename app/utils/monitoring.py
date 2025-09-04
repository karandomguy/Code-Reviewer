from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time
import functools
from typing import Callable, Any
from app.config import settings
from app.utils.logging import logger
import inspect

# Metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration')
ANALYSIS_COUNT = Counter('pr_analysis_total', 'Total PR analyses', ['status'])
ANALYSIS_DURATION = Histogram('pr_analysis_duration_seconds', 'PR analysis duration')
QUEUE_SIZE = Gauge('celery_queue_size', 'Celery queue size', ['queue'])
ACTIVE_WORKERS = Gauge('celery_active_workers', 'Active Celery workers')
ERROR_COUNT = Counter('errors_total', 'Total errors', ['error_type'])

def track_time(metric: Histogram):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                metric.observe(time.time() - start_time)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                metric.observe(time.time() - start_time)
        
        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
    return decorator

def start_metrics_server():
    if settings.enable_metrics:
        start_http_server(8001)
        logger.info("Metrics server started on port 8001")