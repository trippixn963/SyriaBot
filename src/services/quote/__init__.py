"""
SyriaBot - Quote Package
========================

Quote image generation service.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from src.services.quote.service import (
    QuoteService,
    QuoteResult,
    quote_service,
)
from src.services.quote.views import QuoteView

__all__ = [
    "QuoteService",
    "QuoteResult",
    "quote_service",
    "QuoteView",
]
