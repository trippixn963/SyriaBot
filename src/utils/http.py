"""
SyriaBot - HTTP Utilities
=========================

Shared HTTP session for all services.

Author: حَـــــنَّـــــا
"""

import aiohttp

from src.core.logger import log
from src.core.constants import HTTP_DOWNLOAD_TIMEOUT_TOTAL, HTTP_DOWNLOAD_TIMEOUT_CONNECT

# Timeout for downloads
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(
    total=HTTP_DOWNLOAD_TIMEOUT_TOTAL,
    connect=HTTP_DOWNLOAD_TIMEOUT_CONNECT
)


class HTTPSessionManager:
    """Lazy-initialized HTTP session manager."""

    _session: aiohttp.ClientSession | None = None

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            log.info("HTTP session created")
        return self._session

    def get(self, url: str, **kwargs):
        """Return a GET request context manager (use with async with)."""
        return self.session.get(url, **kwargs)

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            log.info("HTTP session closed")


# Global instance
http_session = HTTPSessionManager()
