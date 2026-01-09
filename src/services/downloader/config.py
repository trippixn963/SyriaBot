"""
SyriaBot - Downloader Configuration
===================================

Constants, patterns, and data classes for the downloader service.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# =============================================================================
# Paths
# =============================================================================

# yt-dlp path from the same venv as the running Python
YTDLP_PATH = str(Path(sys.executable).parent / "yt-dlp")

# gallery-dl for image downloads (fallback when yt-dlp fails on images)
GALLERY_DL_PATH = "/usr/bin/gallery-dl"

# Cookies file for Instagram authentication
COOKIES_FILE = Path(__file__).parent.parent.parent.parent / "cookies.txt"

# Cobalt API - local self-hosted instance
COBALT_API_URL = "http://localhost:9000"

# Temp directory for downloads
TEMP_DIR = Path(tempfile.gettempdir()) / "syria_dl"


# =============================================================================
# Size Limits
# =============================================================================

MAX_FILE_SIZE_MB = 24  # Leave headroom under Discord's 25MB limit


# =============================================================================
# File Extensions
# =============================================================================

# Video file extensions (frozen set for O(1) lookup)
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"})

# Image file extensions
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})


# =============================================================================
# Platform Detection Patterns
# =============================================================================

# Pre-compiled regex patterns for each platform
PLATFORM_PATTERNS = {
    "instagram": [
        re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|reels|stories)/[\w-]+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/[\w.]+/(?:p|reel)/[\w-]+", re.IGNORECASE),
    ],
    "twitter": [
        re.compile(r"(?:https?://)?(?:www\.)?(?:twitter|x)\.com/\w+/status/\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:mobile\.)?(?:twitter|x)\.com/\w+/status/\d+", re.IGNORECASE),
    ],
    "tiktok": [
        re.compile(r"(?:https?://)?(?:www\.)?tiktok\.com/@[\w.]+/video/\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:vm|vt)\.tiktok\.com/[\w]+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?tiktok\.com/t/[\w]+", re.IGNORECASE),
    ],
    "reddit": [
        re.compile(r"(?:https?://)?(?:www\.)?reddit\.com/r/\w+/comments/\w+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:old\.)?reddit\.com/r/\w+/comments/\w+", re.IGNORECASE),
        re.compile(r"(?:https?://)?v\.redd\.it/\w+", re.IGNORECASE),
    ],
    "facebook": [
        re.compile(r"(?:https?://)?(?:www\.)?facebook\.com/.+/videos/\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?facebook\.com/watch/?\?v=\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?facebook\.com/reel/\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?fb\.watch/[\w-]+", re.IGNORECASE),
    ],
    "snapchat": [
        re.compile(r"(?:https?://)?(?:www\.)?snapchat\.com/spotlight/[\w-]+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?snapchat\.com/t/[\w-]+", re.IGNORECASE),
    ],
    "twitch": [
        re.compile(r"(?:https?://)?(?:www\.)?twitch\.tv/\w+/clip/[\w-]+", re.IGNORECASE),
        re.compile(r"(?:https?://)?clips\.twitch\.tv/[\w-]+", re.IGNORECASE),
    ],
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    files: list[Path]
    platform: str
    error: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================

def get_platform(url: str) -> Optional[str]:
    """Detect which platform a URL belongs to."""
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if pattern.match(url):
                return platform
    return None
