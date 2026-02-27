"""
SyriaBot - Quote Package
========================

Quote image generation service.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from .service import (
    QuoteService,
    QuoteResult,
    quote_service,
)
from .views import QuoteView

__all__ = [
    "QuoteService",
    "QuoteResult",
    "quote_service",
    "QuoteView",
]
