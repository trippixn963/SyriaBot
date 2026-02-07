"""
SyriaBot - Rate Limiting Middleware
===================================

Token bucket rate limiting for API endpoints.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from src.core.logger import logger
from src.api.config import get_api_config


# =============================================================================
# Token Bucket
# =============================================================================

@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""

    capacity: int
    tokens: float = field(default=0)
    last_update: float = field(default_factory=time.time)
    refill_rate: float = 1.0  # tokens per second

    def __post_init__(self):
        self.tokens = float(self.capacity)

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens from the bucket."""
        now = time.time()
        elapsed = now - self.last_update
        self.last_update = now

        # Refill tokens
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    @property
    def retry_after(self) -> float:
        """Calculate seconds until a token is available."""
        if self.tokens >= 1:
            return 0
        return (1 - self.tokens) / self.refill_rate


# =============================================================================
# Rate Limiter
# =============================================================================

class RateLimiter:
    """
    Manages rate limiting across multiple clients with LRU eviction.
    """

    MAX_TRACKED_IPS = 10000

    def __init__(
        self,
        default_limit: int = 60,
        default_window: int = 60,
        burst_limit: int = 10,
    ):
        self._default_limit = default_limit
        self._default_window = default_window
        self._burst_limit = burst_limit
        # Use OrderedDict for LRU eviction
        self._buckets: OrderedDict[str, TokenBucket] = OrderedDict()
        self._last_cleanup = time.time()
        self._cleanup_interval = 120  # 2 minutes

    def _get_bucket_key(self, client_ip: str, path: str) -> str:
        """Generate a unique key for the rate limit bucket."""
        # Normalize path to group similar endpoints
        normalized = self._normalize_path(path)
        return f"ip:{client_ip}:{normalized}"

    def _normalize_path(self, path: str) -> str:
        """Normalize path for rate limiting (group by resource type)."""
        parts = path.rstrip("/").split("/")
        normalized = []
        for part in parts:
            if not part:
                continue
            # Check if this looks like an ID (numeric)
            if part.isdigit():
                normalized.append("{id}")
            else:
                normalized.append(part)
        return "/" + "/".join(normalized)

    def _cleanup_stale_buckets(self) -> None:
        """Remove buckets that haven't been used recently."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        self._last_cleanup = now
        stale_threshold = now - 120  # 2 minutes

        stale_keys = [
            key for key, bucket in self._buckets.items()
            if bucket.last_update < stale_threshold
        ]

        for key in stale_keys:
            del self._buckets[key]

        if stale_keys:
            logger.debug("Rate Limit Cleanup", [
                ("Removed", str(len(stale_keys))),
                ("Remaining", str(len(self._buckets))),
            ])

    def _evict_if_needed(self) -> None:
        """Evict oldest entries if we exceed max tracked IPs."""
        if len(self._buckets) > self.MAX_TRACKED_IPS:
            # Remove oldest 10%
            evict_count = max(1, self.MAX_TRACKED_IPS // 10)
            for _ in range(evict_count):
                if self._buckets:
                    self._buckets.popitem(last=False)

    def check(
        self,
        client_ip: str,
        path: str,
    ) -> tuple[bool, Optional[int], int, int]:
        """
        Check if a request should be allowed.

        Returns:
            Tuple of (allowed, retry_after, remaining, limit)
        """
        self._cleanup_stale_buckets()

        key = self._get_bucket_key(client_ip, path)

        if key in self._buckets:
            # Move to end for LRU
            self._buckets.move_to_end(key)
        else:
            self._buckets[key] = TokenBucket(
                capacity=self._default_limit,
                refill_rate=self._default_limit / self._default_window,
            )
            self._evict_if_needed()

        bucket = self._buckets[key]
        allowed = bucket.consume()

        return (
            allowed,
            int(bucket.retry_after) + 1 if not allowed else None,
            int(bucket.tokens),
            self._default_limit,
        )


# =============================================================================
# Middleware
# =============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.
    """

    def __init__(self, app, rate_limiter: Optional[RateLimiter] = None):
        super().__init__(app)
        self._limiter = rate_limiter or get_rate_limiter()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ("/health", "/api/syria/health"):
            return await call_next(request)

        # Get client info
        client_ip = self._get_client_ip(request)
        path = request.url.path

        # Check rate limit
        allowed, retry_after, remaining, limit = self._limiter.check(client_ip, path)

        if not allowed:
            logger.tree("Rate Limit Exceeded", [
                ("IP", client_ip),
                ("Path", path[:50]),
                ("Retry After", f"{retry_after}s"),
            ], emoji="⚠️")

            response = Response(
                content='{"error": "Rate limit exceeded", "retry_after": ' + str(retry_after) + '}',
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
            )
            response.headers["Retry-After"] = str(retry_after)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = "0"
            return response

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

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


# =============================================================================
# Singleton
# =============================================================================

_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        config = get_api_config()
        _rate_limiter = RateLimiter(
            default_limit=config.rate_limit_requests,
            default_window=config.rate_limit_window,
            burst_limit=config.rate_limit_burst,
        )
    return _rate_limiter


__all__ = ["RateLimitMiddleware", "RateLimiter", "get_rate_limiter"]
