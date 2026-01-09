"""
SyriaBot - Translate Package
============================

Translation service with multiple backends.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from src.services.translate.service import (
    TranslateService,
    TranslationResult,
    translate_service,
    LANGUAGES,
    LANGUAGE_ALIASES,
    find_similar_language,
    strip_discord_tokens,
)
from src.services.translate.views import (
    TranslateView,
    LanguageSelect,
    create_translate_embed,
    PRIORITY_LANGUAGES,
)

__all__ = [
    "TranslateService",
    "TranslationResult",
    "translate_service",
    "LANGUAGES",
    "LANGUAGE_ALIASES",
    "find_similar_language",
    "strip_discord_tokens",
    "TranslateView",
    "LanguageSelect",
    "create_translate_embed",
    "PRIORITY_LANGUAGES",
]
