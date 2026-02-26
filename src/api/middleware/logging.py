"""
SyriaBot - Logging Middleware
=============================

Request/response logging for API monitoring.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.logger import logger


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for request/response logging.

    Features:
    - Request ID generation and tracking
    - Request timing
    - Error logging
    """

    # Paths to skip logging entirely (high-frequency, low-value)
    SKIP_PATHS = {
        "/health",
        "/api/syria/health",
    }

    # Path prefixes to skip
    SKIP_PREFIXES = (
        "/favicon.ico",
        "/robots.txt",
    )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip logging for certain paths
        path = request.url.path
        if path in self.SKIP_PATHS or path.startswith(self.SKIP_PREFIXES):
            return await call_next(request)

        # Generate request ID
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        # Record start time
        start_time = time.time()

        # Get request info
        method = request.method
        client_ip = self._get_client_ip(request)

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log error
            duration_ms = (time.time() - start_time) * 1000
            logger.error("API Error", [
                ("ID", request_id),
                ("Method", method),
                ("Path", path[:50]),
                ("Error", str(e)[:50]),
                ("Duration", f"{duration_ms:.0f}ms"),
            ])
            raise

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Log response based on status code
        status = response.status_code
        log_data = [
            ("ID", request_id),
            ("Method", method),
            ("Path", path[:50]),
            ("Status", str(status)),
            ("Duration", f"{duration_ms:.0f}ms"),
            ("IP", client_ip),
        ]

        if status >= 500:
            logger.error("API Response", log_data)
        elif status in (403, 429):
            logger.warning("API Response", log_data)
        elif status >= 400:
            # 401s and other 4xx errors are debug level (expected behavior)
            pass
        else:
            # Success responses - only log if slow (>500ms)
            if duration_ms > 500:
                logger.debug("API Response (Slow)", log_data)

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, considering proxies."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        if request.client:
            return request.client.host
        return "unknown"


__all__ = ["LoggingMiddleware"]
