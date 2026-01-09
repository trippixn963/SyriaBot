"""
SyriaBot - Downloader Module
============================

Downloads media from social media platforms using Cobalt API.
Falls back to yt-dlp if Cobalt fails.

Supported platforms:
- Instagram (posts, reels, stories)
- Twitter/X
- TikTok
- Reddit
- Facebook
- Snapchat
- Twitch clips

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from .config import DownloadResult
from .service import DownloaderService

# Global instance
downloader = DownloaderService()

__all__ = ["downloader", "DownloaderService", "DownloadResult"]
