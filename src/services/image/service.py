"""
SyriaBot - Image Search Service
===============================

Image search using Google Custom Search API.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Optional
import aiohttp

from src.core.logger import logger
from src.core.config import config
from src.utils.http import http_session


# Max query length to prevent abuse
MAX_QUERY_LENGTH = 200

# Minimum image dimensions to filter out thumbnails/icons
MIN_IMAGE_WIDTH = 200
MIN_IMAGE_HEIGHT = 200


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
    thumbnail_url: str = ""  # Google-hosted thumbnail (always works)


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
    """
    Service for searching images via Google Custom Search API.

    DESIGN:
        Wraps Google Custom Search JSON API for image queries.
        Returns structured results with thumbnails for preview.
        Supports SafeSearch filtering (off/medium/high).
    """

    GOOGLE_API_URL: str = "https://www.googleapis.com/customsearch/v1"

    def __init__(self) -> None:
        """
        Initialize the image search service.

        Checks for required API credentials (GOOGLE_API_KEY, GOOGLE_CX).
        Service is disabled if credentials are missing.
        """
        self._available: bool = bool(config.GOOGLE_API_KEY and config.GOOGLE_CX)

        if self._available:
            logger.tree("Image Service Initialized", [
                ("API", "Google Custom Search"),
                ("Status", "Ready"),
            ], emoji="✅")
        else:
            logger.tree("Image Service Unavailable", [
                ("Reason", "Missing GOOGLE_API_KEY or GOOGLE_CX"),
            ], emoji="⚠️")

    @property
    def is_available(self) -> bool:
        return self._available

    async def search(
        self,
        query: str,
        num_results: int = 10,
        safe_search: str = "medium",
        img_size: str = "large",
        start_index: int = 1,
    ) -> ImageSearchResult:
        """
        Search for images using Google Custom Search API.

        Args:
            query: Search query
            num_results: Number of results to fetch (max 10 per request)
            safe_search: SafeSearch level (off, medium, high)
            img_size: Image size filter (small, medium, large, xlarge, xxlarge)
            start_index: Starting index for pagination (1-based)

        Returns:
            ImageSearchResult with list of images
        """
        if not self._available:
            logger.tree("Image Search Unavailable", [
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
            logger.tree("Image Search Query Truncated", [
                ("Original Length", str(len(query))),
                ("Truncated To", str(MAX_QUERY_LENGTH)),
            ], emoji="⚠️")
            query = query[:MAX_QUERY_LENGTH]

        logger.tree("Image Search API Call", [
            ("Query", query[:50] + "..." if len(query) > 50 else query),
            ("Results Requested", str(num_results)),
            ("SafeSearch", safe_search),
            ("Size", img_size),
            ("Start Index", str(start_index)),
        ], emoji="🔍")

        # Map safe search levels
        safe_map: dict[str, str] = {
            "off": "off",
            "medium": "medium",
            "high": "high",
        }
        safe_param: str = safe_map.get(safe_search, "medium")

        # Map image size levels
        size_map: dict[str, str] = {
            "small": "small",
            "medium": "medium",
            "large": "large",
            "xlarge": "xlarge",
            "xxlarge": "xxlarge",
        }
        size_param: str = size_map.get(img_size, "large")

        # Google CSE params
        params: dict[str, Any] = {
            "key": config.GOOGLE_API_KEY,
            "cx": config.GOOGLE_CX,
            "q": query,
            "searchType": "image",
            "num": min(num_results, 10),  # Max 10 per request
            "safe": safe_param,
            "imgSize": size_param,
            "start": start_index,
        }

        try:
            async with http_session.session.get(
                self.GOOGLE_API_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    error_data = await resp.text()
                    logger.tree("Image Search API Error", [
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
            logger.tree("Image Search Timeout", [
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
            logger.error_tree("Image Search Error", e, [
                ("Query", query[:50]),
            ])
            return ImageSearchResult(
                success=False,
                query=query,
                images=[],
                total_results=0,
                error=str(e)
            )

        # Parse results (filter out small images)
        images: list[ImageResult] = []
        items: list[dict[str, Any]] = data.get("items", [])
        skipped_small = 0

        for item in items:
            img_info: dict[str, Any] = item.get("image", {})
            width = img_info.get("width", 0)
            height = img_info.get("height", 0)

            # Skip images that are too small
            if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
                skipped_small += 1
                continue

            images.append(ImageResult(
                url=item.get("link", ""),
                title=item.get("title", "No title"),
                source_url=item.get("image", {}).get("contextLink", ""),
                width=width,
                height=height,
                thumbnail_url=img_info.get("thumbnailLink", ""),  # Google-hosted
            ))

        if skipped_small > 0:
            logger.tree("Image Search Filtered Small", [
                ("Query", query[:50]),
                ("Skipped", str(skipped_small)),
                ("Min Size", f"{MIN_IMAGE_WIDTH}x{MIN_IMAGE_HEIGHT}"),
            ], emoji="📐")

        if not images:
            logger.tree("Image Search No Results", [
                ("Query", query[:50]),
            ], emoji="⚠️")
            return ImageSearchResult(
                success=False,
                query=query,
                images=[],
                total_results=0,
                error="No images found"
            )

        logger.tree("Image Search API Success", [
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
image_service: ImageService = ImageService()
