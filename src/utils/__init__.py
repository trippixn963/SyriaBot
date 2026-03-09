"""
SyriaBot - Utils Package
========================

Shared utilities for HTTP and text processing.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from src.utils.http import http_session, DOWNLOAD_TIMEOUT
from src.utils.text import wrap_text

__all__ = [
    # HTTP
    "http_session",
    "DOWNLOAD_TIMEOUT",
    # Text
    "wrap_text",
]
