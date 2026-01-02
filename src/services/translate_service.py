"""
SyriaBot - Translation Service
==============================

Translation service using Google Translate.

Author: حَـــــنَّـــــا
"""

import asyncio
import aiohttp
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from deep_translator import GoogleTranslator
from langdetect import detect, LangDetectException

from src.core.logger import log
from src.core.config import config
from src.utils.http import http_session


# =============================================================================
# Language Data
# =============================================================================

LANGUAGES: Dict[str, Tuple[str, str]] = {
    "ar": ("Arabic", "🇸🇦"),
    "en": ("English", "🇺🇸"),
    "es": ("Spanish", "🇪🇸"),
    "fr": ("French", "🇫🇷"),
    "de": ("German", "🇩🇪"),
    "it": ("Italian", "🇮🇹"),
    "pt": ("Portuguese", "🇵🇹"),
    "ru": ("Russian", "🇷🇺"),
    "zh-CN": ("Chinese (Simplified)", "🇨🇳"),
    "zh-TW": ("Chinese (Traditional)", "🇹🇼"),
    "ja": ("Japanese", "🇯🇵"),
    "ko": ("Korean", "🇰🇷"),
    "tr": ("Turkish", "🇹🇷"),
    "nl": ("Dutch", "🇳🇱"),
    "pl": ("Polish", "🇵🇱"),
    "uk": ("Ukrainian", "🇺🇦"),
    "hi": ("Hindi", "🇮🇳"),
    "iw": ("Hebrew", "🇮🇱"),
    "fa": ("Persian", "🇮🇷"),
    "ur": ("Urdu", "🇵🇰"),
    "sv": ("Swedish", "🇸🇪"),
    "da": ("Danish", "🇩🇰"),
    "no": ("Norwegian", "🇳🇴"),
    "fi": ("Finnish", "🇫🇮"),
    "el": ("Greek", "🇬🇷"),
    "cs": ("Czech", "🇨🇿"),
    "ro": ("Romanian", "🇷🇴"),
    "hu": ("Hungarian", "🇭🇺"),
    "th": ("Thai", "🇹🇭"),
    "vi": ("Vietnamese", "🇻🇳"),
    "id": ("Indonesian", "🇮🇩"),
    "ms": ("Malay", "🇲🇾"),
}

LANGUAGE_ALIASES: Dict[str, str] = {
    "arabic": "ar",
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "russian": "ru",
    "chinese": "zh-CN",
    "chinese simplified": "zh-CN",
    "simplified chinese": "zh-CN",
    "chinese traditional": "zh-TW",
    "traditional chinese": "zh-TW",
    "taiwanese": "zh-TW",
    "japanese": "ja",
    "korean": "ko",
    "turkish": "tr",
    "dutch": "nl",
    "polish": "pl",
    "ukrainian": "uk",
    "hindi": "hi",
    "hebrew": "iw",
    "persian": "fa",
    "farsi": "fa",
    "urdu": "ur",
    "swedish": "sv",
    "danish": "da",
    "norwegian": "no",
    "finnish": "fi",
    "greek": "el",
    "czech": "cs",
    "romanian": "ro",
    "hungarian": "hu",
    "thai": "th",
    "vietnamese": "vi",
    "indonesian": "id",
    "malay": "ms",
}


def find_similar_language(lang_input: str) -> Optional[Tuple[str, str, str]]:
    """Find a similar language to what the user typed."""
    lang_lower = lang_input.lower().strip()

    for alias, code in LANGUAGE_ALIASES.items():
        if alias.startswith(lang_lower) or lang_lower.startswith(alias[:3]):
            name, flag = LANGUAGES[code]
            return (code, name, flag)

    for code, (name, flag) in LANGUAGES.items():
        name_lower = name.lower()
        if name_lower.startswith(lang_lower) or lang_lower.startswith(name_lower[:3]):
            return (code, name, flag)

    return None


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TranslationResult:
    """Result of a translation operation."""
    success: bool
    original_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    source_name: str
    target_name: str
    source_flag: str
    target_flag: str
    error: Optional[str] = None


# =============================================================================
# Translation Service
# =============================================================================

class TranslateService:
    """Service for translating text."""

    def __init__(self):
        pass

    def resolve_language(self, lang_input: str) -> Optional[str]:
        """Resolve a language input to a language code."""
        lang_input = lang_input.strip()
        lang_lower = lang_input.lower()

        if lang_input in LANGUAGES:
            return lang_input

        for code in LANGUAGES:
            if code.lower() == lang_lower:
                return code

        if lang_lower in LANGUAGE_ALIASES:
            return LANGUAGE_ALIASES[lang_lower]

        return None

    def get_language_info(self, lang_code: str) -> Tuple[str, str]:
        """Get language name and flag for a code."""
        if lang_code in LANGUAGES:
            return LANGUAGES[lang_code]
        lang_lower = lang_code.lower()
        for code, info in LANGUAGES.items():
            if code.lower() == lang_lower:
                return info
        return (lang_code.upper(), "🌐")

    def detect_language(self, text: str) -> Optional[str]:
        """Detect the language of text."""
        try:
            detected = detect(text)
            if detected == "zh-cn":
                return "zh-CN"
            if detected == "zh-tw":
                return "zh-TW"
            return detected
        except LangDetectException:
            return None

    async def translate(
        self,
        text: str,
        target_lang: str = "en",
        source_lang: str = "auto"
    ) -> TranslationResult:
        """Translate text to target language."""
        resolved_target = self.resolve_language(target_lang)
        if not resolved_target:
            return TranslationResult(
                success=False,
                original_text=text,
                translated_text="",
                source_lang="",
                target_lang=target_lang,
                source_name="",
                target_name="",
                source_flag="",
                target_flag="",
                error=f"Unknown language: {target_lang}"
            )

        if source_lang == "auto":
            detected = self.detect_language(text)
            source_lang = detected or "auto"

        log.tree("Translating", [
            ("Text", text[:50] + "..." if len(text) > 50 else text),
            ("From", source_lang),
            ("To", resolved_target),
        ], emoji="🌐")

        try:
            translator = GoogleTranslator(source=source_lang, target=resolved_target)
            translated = await asyncio.to_thread(translator.translate, text)

            source_name, source_flag = self.get_language_info(source_lang)
            target_name, target_flag = self.get_language_info(resolved_target)

            log.tree("Translation Complete", [
                ("From", f"{source_name} {source_flag}"),
                ("To", f"{target_name} {target_flag}"),
                ("Result Length", str(len(translated))),
            ], emoji="✅")

            return TranslationResult(
                success=True,
                original_text=text,
                translated_text=translated,
                source_lang=source_lang,
                target_lang=resolved_target,
                source_name=source_name,
                target_name=target_name,
                source_flag=source_flag,
                target_flag=target_flag,
            )

        except Exception as e:
            log.error_tree("Translation Failed", e, [
                ("Text", text[:50]),
                ("Target", resolved_target),
            ])

            return TranslationResult(
                success=False,
                original_text=text,
                translated_text="",
                source_lang=source_lang,
                target_lang=resolved_target,
                source_name="",
                target_name="",
                source_flag="",
                target_flag="",
                error=str(e)
            )


    async def translate_ai(
        self,
        text: str,
        target_lang: str = "en",
    ) -> TranslationResult:
        """Translate text using GPT-4o-mini for higher quality."""
        resolved_target = self.resolve_language(target_lang)
        if not resolved_target:
            return TranslationResult(
                success=False,
                original_text=text,
                translated_text="",
                source_lang="",
                target_lang=target_lang,
                source_name="",
                target_name="",
                source_flag="",
                target_flag="",
                error=f"Unknown language: {target_lang}"
            )

        target_name, target_flag = self.get_language_info(resolved_target)

        # Detect source language
        detected = self.detect_language(text)
        source_lang = detected or "auto"
        source_name, source_flag = self.get_language_info(source_lang)

        log.tree("AI Translating", [
            ("Text", text[:50] + "..." if len(text) > 50 else text),
            ("From", source_lang),
            ("To", resolved_target),
        ], emoji="🤖")

        if not config.OPENAI_API_KEY:
            log.tree("AI Translation Failed", [
                ("Reason", "No OpenAI API key configured"),
            ], emoji="❌")
            return TranslationResult(
                success=False,
                original_text=text,
                translated_text="",
                source_lang=source_lang,
                target_lang=resolved_target,
                source_name=source_name,
                target_name=target_name,
                source_flag=source_flag,
                target_flag=target_flag,
                error="AI translation not configured"
            )

        try:
            async with http_session.session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": f"You are a professional translator. Translate the following text to {target_name}. Only respond with the translation, nothing else. Preserve the original formatting, tone, and style."
                        },
                        {
                            "role": "user",
                            "content": text
                        }
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    log.tree("AI Translation API Error", [
                        ("Status", str(resp.status)),
                        ("Error", error_text[:100]),
                    ], emoji="❌")
                    return TranslationResult(
                        success=False,
                        original_text=text,
                        translated_text="",
                        source_lang=source_lang,
                        target_lang=resolved_target,
                        source_name=source_name,
                        target_name=target_name,
                        source_flag=source_flag,
                        target_flag=target_flag,
                        error="AI translation failed"
                    )

                data = await resp.json()
                translated = data["choices"][0]["message"]["content"].strip()

                log.tree("AI Translation Complete", [
                    ("From", f"{source_name} {source_flag}"),
                    ("To", f"{target_name} {target_flag}"),
                    ("Result Length", str(len(translated))),
                ], emoji="✅")

                return TranslationResult(
                    success=True,
                    original_text=text,
                    translated_text=translated,
                    source_lang=source_lang,
                    target_lang=resolved_target,
                    source_name=source_name,
                    target_name=target_name,
                    source_flag=source_flag,
                    target_flag=target_flag,
                )

        except asyncio.TimeoutError:
            log.tree("AI Translation Timeout", [
                ("Text", text[:50]),
            ], emoji="⏳")
            return TranslationResult(
                success=False,
                original_text=text,
                translated_text="",
                source_lang=source_lang,
                target_lang=resolved_target,
                source_name=source_name,
                target_name=target_name,
                source_flag=source_flag,
                target_flag=target_flag,
                error="AI translation timed out"
            )
        except Exception as e:
            log.error_tree("AI Translation Failed", e, [
                ("Text", text[:50]),
                ("Target", resolved_target),
            ])
            return TranslationResult(
                success=False,
                original_text=text,
                translated_text="",
                source_lang=source_lang,
                target_lang=resolved_target,
                source_name=source_name,
                target_name=target_name,
                source_flag=source_flag,
                target_flag=target_flag,
                error=str(e)
            )


# Global instance
translate_service = TranslateService()
