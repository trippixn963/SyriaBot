"""
SyriaBot - HTTP Utilities
=========================

Shared HTTP session for all services with rate limit handling.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import aiohttp
from typing import Optional

from src.core.logger import log
from src.core.constants import HTTP_DOWNLOAD_TIMEOUT_TOTAL, HTTP_DOWNLOAD_TIMEOUT_CONNECT

# Timeout for downloads
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(
    total=HTTP_DOWNLOAD_TIMEOUT_TOTAL,
    connect=HTTP_DOWNLOAD_TIMEOUT_CONNECT
)

# Retry settings
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds
MAX_BACKOFF_DELAY = 300.0  # 5 minutes max


class HTTPSessionManager:
    """Lazy-initialized HTTP session manager for shared aiohttp sessions."""

    _session: aiohttp.ClientSession | None = None

    def __init__(self) -> None:
        """Initialize the session manager with no active session."""
        pass

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            log.tree("HTTP Session", [
                ("Status", "Created"),
            ], emoji="🌐")
        return self._session

    def get(self, url: str, **kwargs) -> aiohttp.client._RequestContextManager:
        """Return a GET request context manager (use with async with)."""
        return self.session.get(url, **kwargs)

    async def get_with_retry(
        self,
        url: str,
        max_retries: int = MAX_RETRIES,
        **kwargs
    ) -> Optional[aiohttp.ClientResponse]:
        """
        GET request with exponential backoff retry on rate limits.

        Args:
            url: URL to fetch
            max_retries: Maximum retry attempts
            **kwargs: Additional arguments passed to session.get()

        Returns:
            Response object or None if all retries failed
        """
        for attempt in range(max_retries):
            try:
                response = await self.session.get(url, **kwargs)

                if response.status == 429:
                    # Consume response body to prevent resource leak
                    await response.read()

                    # Rate limited - use Retry-After header or exponential backoff
                    retry_after = response.headers.get("Retry-After")
                    delay = RETRY_BASE_DELAY * (2 ** attempt)  # Default fallback
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            pass  # Use default backoff if malformed

                    # Cap the delay to prevent excessive waits
                    delay = min(delay, MAX_BACKOFF_DELAY)

                    log.tree("HTTP Rate Limited", [
                        ("URL", url[:50]),
                        ("Attempt", f"{attempt + 1}/{max_retries}"),
                        ("Retry After", f"{delay:.1f}s"),
                    ], emoji="⏳")

                    await asyncio.sleep(delay)
                    continue

                return response

            except asyncio.TimeoutError:
                log.tree("HTTP Request Timeout", [
                    ("URL", url[:50]),
                    ("Attempt", f"{attempt + 1}/{max_retries}"),
                ], emoji="⏳")
            except aiohttp.ClientError as e:
                log.tree("HTTP Request Error", [
                    ("URL", url[:50]),
                    ("Error", str(e)[:50]),
                    ("Attempt", f"{attempt + 1}/{max_retries}"),
                ], emoji="⚠️")

            # Exponential backoff before retry (capped)
            if attempt < max_retries - 1:
                delay = min(RETRY_BASE_DELAY * (2 ** attempt), MAX_BACKOFF_DELAY)
                await asyncio.sleep(delay)

        log.tree("HTTP Request Failed", [
            ("URL", url[:50]),
            ("Reason", "All retries exhausted"),
        ], emoji="❌")
        return None

    async def post_with_retry(
        self,
        url: str,
        max_retries: int = MAX_RETRIES,
        **kwargs
    ) -> Optional[aiohttp.ClientResponse]:
        """
        POST request with exponential backoff retry on rate limits.

        Args:
            url: URL to post to
            max_retries: Maximum retry attempts
            **kwargs: Additional arguments passed to session.post()

        Returns:
            Response object or None if all retries failed
        """
        for attempt in range(max_retries):
            try:
                response = await self.session.post(url, **kwargs)

                if response.status == 429:
                    # Consume response body to prevent resource leak
                    await response.read()

                    retry_after = response.headers.get("Retry-After")
                    delay = RETRY_BASE_DELAY * (2 ** attempt)  # Default fallback
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            pass  # Use default backoff if malformed

                    # Cap the delay to prevent excessive waits
                    delay = min(delay, MAX_BACKOFF_DELAY)

                    log.tree("HTTP Rate Limited", [
                        ("URL", url[:50]),
                        ("Attempt", f"{attempt + 1}/{max_retries}"),
                        ("Retry After", f"{delay:.1f}s"),
                    ], emoji="⏳")

                    await asyncio.sleep(delay)
                    continue

                return response

            except asyncio.TimeoutError:
                log.tree("HTTP Request Timeout", [
                    ("URL", url[:50]),
                    ("Attempt", f"{attempt + 1}/{max_retries}"),
                ], emoji="⏳")
            except aiohttp.ClientError as e:
                log.tree("HTTP Request Error", [
                    ("URL", url[:50]),
                    ("Error", str(e)[:50]),
                    ("Attempt", f"{attempt + 1}/{max_retries}"),
                ], emoji="⚠️")

            # Exponential backoff before retry (capped)
            if attempt < max_retries - 1:
                delay = min(RETRY_BASE_DELAY * (2 ** attempt), MAX_BACKOFF_DELAY)
                await asyncio.sleep(delay)

        log.tree("HTTP Request Failed", [
            ("URL", url[:50]),
            ("Reason", "All retries exhausted"),
        ], emoji="❌")
        return None

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            log.tree("HTTP Session", [
                ("Status", "Closed"),
            ], emoji="🔌")


# Global instance
http_session = HTTPSessionManager()
