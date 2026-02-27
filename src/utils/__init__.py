"""
SyriaBot - Utils Package
========================

Shared utilities for HTTP, footers, and text processing.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from src.utils.http import http_session, DOWNLOAD_TIMEOUT
from src.utils.footer import (
    init_footer,
    set_footer,
)
from src.utils.text import wrap_text

__all__ = [
    # HTTP
    "http_session",
    "DOWNLOAD_TIMEOUT",
    # Footer
    "init_footer",
    "set_footer",
    # Text
    "wrap_text",
]
