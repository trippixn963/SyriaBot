"""
SyriaBot - Image Search Service
===============================

Image search using Google Custom Search API.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from dataclasses import dataclass
from typing import Optional
import aiohttp

from src.core.logger import log
from src.core.config import config
from src.utils.http import http_session


# Max query length to prevent abuse
MAX_QUERY_LENGTH = 200


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ImageResult:
    """A single image search result."""
    url: str
    title: str
    source_url: str
    width: int
    height: int


@dataclass
class ImageSearchResult:
    """Result of an image search."""
    success: bool
    query: str
    images: list[ImageResult]
    total_results: int
    error: Optional[str] = None


# =============================================================================
# Image Search Service
# =============================================================================

class ImageService:
    """Service for searching images via Google Custom Search API."""

    GOOGLE_API_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self):
        self._available = bool(config.GOOGLE_API_KEY and config.GOOGLE_CX)

        if self._available:
            log.tree("Image Service Initialized", [
                ("API", "Google Custom Search"),
                ("Status", "Ready"),
            ], emoji="✅")
        else:
            log.tree("Image Service Unavailable", [
                ("Reason", "Missing GOOGLE_API_KEY or GOOGLE_CX"),
            ], emoji="⚠️")

    @property
    def is_available(self) -> bool:
        return self._available

    async def search(
        self,
        query: str,
        num_results: int = 10,
        safe_search: str = "medium"
    ) -> ImageSearchResult:
        """
        Search for images using Google Custom Search API.

        Args:
            query: Search query
            num_results: Number of results to fetch (max 10 per request)
            safe_search: SafeSearch level (off, medium, high)

        Returns:
            ImageSearchResult with list of images
        """
        if not self._available:
            log.tree("Image Search Unavailable", [
                ("Query", query[:50]),
                ("Reason", "API not configured"),
            ], emoji="❌")
            return ImageSearchResult(
                success=False,
                query=query,
                images=[],
                total_results=0,
                error="Image search not configured - missing API keys"
            )

        # Validate and truncate query length
        if len(query) > MAX_QUERY_LENGTH:
            log.tree("Image Search Query Truncated", [
                ("Original Length", str(len(query))),
                ("Truncated To", str(MAX_QUERY_LENGTH)),
            ], emoji="⚠️")
            query = query[:MAX_QUERY_LENGTH]

        log.tree("Image Search API Call", [
            ("Query", query[:50] + "..." if len(query) > 50 else query),
            ("Results Requested", str(num_results)),
            ("SafeSearch", safe_search),
        ], emoji="🔍")

        # Map safe search levels
        safe_map = {
            "off": "off",
            "medium": "medium",
            "high": "high",
        }
        safe_param = safe_map.get(safe_search, "medium")

        # Google CSE params
        params = {
            "key": config.GOOGLE_API_KEY,
            "cx": config.GOOGLE_CX,
            "q": query,
            "searchType": "image",
            "num": min(num_results, 10),  # Max 10 per request
            "safe": safe_param,
        }

        try:
            async with http_session.session.get(
                self.GOOGLE_API_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    error_data = await resp.text()
                    log.tree("Image Search API Error", [
                        ("Query", query[:50]),
                        ("Status", str(resp.status)),
                        ("Error", error_data[:100]),
                    ], emoji="❌")
                    return ImageSearchResult(
                        success=False,
                        query=query,
                        images=[],
                        total_results=0,
                        error=f"Google API error: HTTP {resp.status}"
                    )

                data = await resp.json()

        except asyncio.TimeoutError:
            log.tree("Image Search Timeout", [
                ("Query", query[:50]),
                ("Timeout", "10s"),
            ], emoji="⏳")
            return ImageSearchResult(
                success=False,
                query=query,
                images=[],
                total_results=0,
                error="Search timed out. Please try again."
            )
        except Exception as e:
            log.error_tree("Image Search Error", e, [
                ("Query", query[:50]),
            ])
            return ImageSearchResult(
                success=False,
                query=query,
                images=[],
                total_results=0,
                error=str(e)
            )

        # Parse results
        images = []
        items = data.get("items", [])

        for item in items:
            img_info = item.get("image", {})
            images.append(ImageResult(
                url=item.get("link", ""),
                title=item.get("title", "No title"),
                source_url=item.get("image", {}).get("contextLink", ""),
                width=img_info.get("width", 0),
                height=img_info.get("height", 0),
            ))

        if not images:
            log.tree("Image Search No Results", [
                ("Query", query[:50]),
            ], emoji="⚠️")
            return ImageSearchResult(
                success=False,
                query=query,
                images=[],
                total_results=0,
                error="No images found"
            )

        log.tree("Image Search API Success", [
            ("Query", query[:50] + "..." if len(query) > 50 else query),
            ("Results", str(len(images))),
        ], emoji="✅")

        return ImageSearchResult(
            success=True,
            query=query,
            images=images,
            total_results=len(images),
        )


# Global instance
image_service = ImageService()
