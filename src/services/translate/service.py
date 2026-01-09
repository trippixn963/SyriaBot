"""
SyriaBot - Translation Service
==============================

Translation service using Google Translate.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import aiohttp
import re
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from deep_translator import GoogleTranslator
from deep_translator.exceptions import TranslationNotFound
from langdetect import detect, LangDetectException

from src.core.logger import log
from src.core.config import config
from src.utils.http import http_session


# =============================================================================
# Discord Token Handling
# =============================================================================

# Patterns for Discord mentions/emojis to strip from translations
DISCORD_TOKEN_PATTERN = re.compile(
    r'<(?:'
    r'@!?\d+|'           # User mentions: <@123> or <@!123>
    r'@&\d+|'            # Role mentions: <@&123>
    r'#\d+|'             # Channel mentions: <#123>
    r'a?:\w+:\d+'        # Custom emojis: <:name:123> or <a:name:123>
    r')>'
)


def strip_discord_tokens(text: str) -> str:
    """Remove Discord mentions/emojis from text completely."""
    # Remove tokens and clean up extra whitespace
    cleaned = DISCORD_TOKEN_PATTERN.sub('', text)
    # Clean up multiple spaces left behind
    cleaned = re.sub(r' +', ' ', cleaned).strip()
    return cleaned


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
    # Language names
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
    # Country names
    "syria": "ar",
    "syrian": "ar",
    "saudi": "ar",
    "saudi arabia": "ar",
    "egypt": "ar",
    "egyptian": "ar",
    "iraq": "ar",
    "iraqi": "ar",
    "jordan": "ar",
    "jordanian": "ar",
    "lebanon": "ar",
    "lebanese": "ar",
    "palestine": "ar",
    "palestinian": "ar",
    "america": "en",
    "american": "en",
    "usa": "en",
    "uk": "en",
    "british": "en",
    "britain": "en",
    "australia": "en",
    "australian": "en",
    "canada": "en",
    "canadian": "en",
    "spain": "es",
    "mexico": "es",
    "mexican": "es",
    "france": "fr",
    "germany": "de",
    "italy": "it",
    "portugal": "pt",
    "brazil": "pt",
    "brazilian": "pt",
    "russia": "ru",
    "china": "zh-CN",
    "taiwan": "zh-TW",
    "japan": "ja",
    "korea": "ko",
    "south korea": "ko",
    "turkey": "tr",
    "netherlands": "nl",
    "holland": "nl",
    "poland": "pl",
    "ukraine": "uk",
    "india": "hi",
    "indian": "hi",
    "israel": "iw",
    "israeli": "iw",
    "iran": "fa",
    "iranian": "fa",
    "pakistan": "ur",
    "pakistani": "ur",
    "sweden": "sv",
    "denmark": "da",
    "norway": "no",
    "finland": "fi",
    "greece": "el",
    "czechia": "cs",
    "czech republic": "cs",
    "romania": "ro",
    "hungary": "hu",
    "thailand": "th",
    "vietnam": "vi",
    "indonesia": "id",
    "malaysia": "ms",
}


def _fuzzy_match(s1: str, s2: str) -> float:
    """Calculate similarity ratio between two strings (0.0 to 1.0)."""
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0

    # Check prefix match (at least 3 chars)
    if len(s1) >= 3 and len(s2) >= 3:
        if s1.startswith(s2[:3]) or s2.startswith(s1[:3]):
            # Good prefix match
            return 0.85

    # Check if one contains the other
    if s1 in s2 or s2 in s1:
        return 0.8

    # Count matching characters (order-independent for typo tolerance)
    len1, len2 = len(s1), len(s2)
    if abs(len1 - len2) > 2:
        # Allow up to 2 char length difference
        if abs(len1 - len2) > max(len1, len2) // 2:
            return 0.0

    # Count common characters
    chars1 = list(s1)
    chars2 = list(s2)
    common = 0
    for c in chars1:
        if c in chars2:
            common += 1
            chars2.remove(c)

    return common / max(len1, len2)


def find_similar_language(lang_input: str) -> Optional[Tuple[str, str, str]]:
    """Find a similar language to what the user typed using fuzzy matching."""
    lang_lower = lang_input.lower().strip()

    if not lang_lower:
        return None

    best_match = None
    best_score = 0.0
    match_type = None

    # Check exact matches in aliases first
    if lang_lower in LANGUAGE_ALIASES:
        code = LANGUAGE_ALIASES[lang_lower]
        name, flag = LANGUAGES[code]
        log.tree("Language Alias Match", [
            ("Input", lang_input),
            ("Alias", lang_lower),
            ("Resolved", f"{name} ({code}) {flag}"),
        ], emoji="🌐")
        return (code, name, flag)

    # Check exact matches in language codes
    if lang_lower in LANGUAGES:
        name, flag = LANGUAGES[lang_lower]
        log.tree("Language Code Match", [
            ("Input", lang_input),
            ("Code", lang_lower),
            ("Language", f"{name} {flag}"),
        ], emoji="🌐")
        return (lang_lower, name, flag)

    # Fuzzy match against aliases (includes country names)
    for alias, code in LANGUAGE_ALIASES.items():
        score = _fuzzy_match(lang_lower, alias)
        if score > best_score and score >= 0.6:
            best_score = score
            name, flag = LANGUAGES[code]
            best_match = (code, name, flag)
            match_type = ("alias", alias)

    # Fuzzy match against language names
    for code, (name, flag) in LANGUAGES.items():
        score = _fuzzy_match(lang_lower, name.lower())
        if score > best_score and score >= 0.6:
            best_score = score
            best_match = (code, name, flag)
            match_type = ("name", name)

    if best_match:
        log.tree("Language Fuzzy Match", [
            ("Input", lang_input),
            ("Matched", f"{match_type[0]}: {match_type[1]}"),
            ("Score", f"{best_score:.0%}"),
            ("Resolved", f"{best_match[1]} ({best_match[0]}) {best_match[2]}"),
        ], emoji="🔍")
    else:
        log.tree("Language Match Failed", [
            ("Input", lang_input),
            ("Reason", "No match found"),
        ], emoji="⚠️")

    return best_match


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
        """Resolve a language input to a language code using fuzzy matching."""
        lang_input = lang_input.strip()
        lang_lower = lang_input.lower()

        # Exact match on language codes
        if lang_input in LANGUAGES:
            log.tree("Language Resolved", [
                ("Input", lang_input),
                ("Type", "Exact code match"),
                ("Code", lang_input),
            ], emoji="✅")
            return lang_input

        for code in LANGUAGES:
            if code.lower() == lang_lower:
                log.tree("Language Resolved", [
                    ("Input", lang_input),
                    ("Type", "Case-insensitive code match"),
                    ("Code", code),
                ], emoji="✅")
                return code

        # Exact match on aliases (includes country names)
        if lang_lower in LANGUAGE_ALIASES:
            code = LANGUAGE_ALIASES[lang_lower]
            name, flag = LANGUAGES[code]
            log.tree("Language Resolved", [
                ("Input", lang_input),
                ("Type", "Alias/country match"),
                ("Resolved", f"{name} ({code}) {flag}"),
            ], emoji="✅")
            return code

        # Fuzzy match using find_similar_language (logs internally)
        similar = find_similar_language(lang_input)
        if similar:
            return similar[0]  # Return the code

        # find_similar_language already logs failure
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
            # Map language codes to what GoogleTranslator expects
            if detected == "zh-cn":
                return "zh-CN"
            if detected == "zh-tw":
                return "zh-TW"
            if detected == "he":
                return "iw"  # GoogleTranslator uses 'iw' for Hebrew, not 'he'
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

        # Strip Discord mentions/emojis before translation
        cleaned_text = strip_discord_tokens(text)

        if source_lang == "auto":
            detected = self.detect_language(cleaned_text)
            source_lang = detected or "auto"

        log.tree("Translating", [
            ("Text", cleaned_text[:50] + "..." if len(cleaned_text) > 50 else cleaned_text),
            ("From", source_lang),
            ("To", resolved_target),
        ], emoji="🌐")

        # Try DeepL first (higher quality), fall back to Google
        if config.DEEPL_API_KEY:
            result = await self._translate_deepl(cleaned_text, source_lang, resolved_target)
            if result.success:
                return result

        # Google Translate fallback
        return await self._translate_google(cleaned_text, source_lang, resolved_target)


    # DeepL language code mapping (DeepL uses different codes)
    DEEPL_LANG_MAP = {
        "en": "EN",
        "ar": "AR",
        "de": "DE",
        "es": "ES",
        "fr": "FR",
        "it": "IT",
        "ja": "JA",
        "ko": "KO",
        "nl": "NL",
        "pl": "PL",
        "pt": "PT",
        "ru": "RU",
        "zh-CN": "ZH",
        "zh-TW": "ZH",
        "tr": "TR",
        "uk": "UK",
        "iw": "HE",  # Hebrew: iw → HE
        "el": "EL",
        "cs": "CS",
        "da": "DA",
        "fi": "FI",
        "hu": "HU",
        "id": "ID",
        "no": "NB",  # Norwegian → Norwegian Bokmål
        "ro": "RO",
        "sv": "SV",
    }

    async def _translate_deepl(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> TranslationResult:
        """Translate using DeepL API (higher quality)."""
        # Map to DeepL language codes
        deepl_target = self.DEEPL_LANG_MAP.get(target_lang, target_lang.upper())
        deepl_source = self.DEEPL_LANG_MAP.get(source_lang) if source_lang != "auto" else None

        try:
            params = {
                "text": text,
                "target_lang": deepl_target,
            }
            if deepl_source:
                params["source_lang"] = deepl_source

            async with http_session.session.post(
                "https://api-free.deepl.com/v2/translate",
                headers={
                    "Authorization": f"DeepL-Auth-Key {config.DEEPL_API_KEY}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    log.tree("DeepL Unavailable", [
                        ("Status", str(resp.status)),
                        ("Fallback", "Google Translate"),
                    ], emoji="🔄")
                    return TranslationResult(
                        success=False,
                        original_text=text,
                        translated_text="",
                        source_lang=source_lang,
                        target_lang=target_lang,
                        source_name="",
                        target_name="",
                        source_flag="",
                        target_flag="",
                        error=f"DeepL API error: {resp.status}"
                    )

                data = await resp.json()
                translations = data.get("translations", [])
                if not translations:
                    return TranslationResult(
                        success=False,
                        original_text=text,
                        translated_text="",
                        source_lang=source_lang,
                        target_lang=target_lang,
                        source_name="",
                        target_name="",
                        source_flag="",
                        target_flag="",
                        error="DeepL returned no translation"
                    )

                translated = translations[0].get("text", "")
                detected_source = translations[0].get("detected_source_language", "").lower()

                # Map DeepL detected language back to our codes
                if detected_source == "he":
                    detected_source = "iw"
                elif detected_source == "nb":
                    detected_source = "no"
                elif detected_source == "zh":
                    detected_source = "zh-CN"

                if source_lang == "auto" and detected_source:
                    source_lang = detected_source

                source_name, source_flag = self.get_language_info(source_lang)
                target_name, target_flag = self.get_language_info(target_lang)

                log.tree("DeepL Translation Complete", [
                    ("From", f"{source_name} {source_flag}"),
                    ("To", f"{target_name} {target_flag}"),
                    ("Chars Used", str(len(text))),
                    ("Result Length", str(len(translated))),
                ], emoji="✅")

                return TranslationResult(
                    success=True,
                    original_text=text,
                    translated_text=translated,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    source_name=source_name,
                    target_name=target_name,
                    source_flag=source_flag,
                    target_flag=target_flag,
                )

        except asyncio.TimeoutError:
            log.tree("DeepL Timeout", [
                ("Text Length", str(len(text))),
            ], emoji="⏳")
            return TranslationResult(
                success=False,
                original_text=text,
                translated_text="",
                source_lang=source_lang,
                target_lang=target_lang,
                source_name="",
                target_name="",
                source_flag="",
                target_flag="",
                error="DeepL request timed out"
            )
        except Exception as e:
            log.error_tree("DeepL Translation Failed", e, [
                ("Text", text[:50]),
            ])
            return TranslationResult(
                success=False,
                original_text=text,
                translated_text="",
                source_lang=source_lang,
                target_lang=target_lang,
                source_name="",
                target_name="",
                source_flag="",
                target_flag="",
                error=str(e)
            )

    async def _translate_google(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> TranslationResult:
        """Translate using Google Translate (fallback)."""
        try:
            translator = GoogleTranslator(source=source_lang, target=target_lang)
            translated = await asyncio.to_thread(translator.translate, text)

            source_name, source_flag = self.get_language_info(source_lang)
            target_name, target_flag = self.get_language_info(target_lang)

            log.tree("Google Translation Complete", [
                ("From", f"{source_name} {source_flag}"),
                ("To", f"{target_name} {target_flag}"),
                ("Result Length", str(len(translated))),
            ], emoji="✅")

            return TranslationResult(
                success=True,
                original_text=text,
                translated_text=translated,
                source_lang=source_lang,
                target_lang=target_lang,
                source_name=source_name,
                target_name=target_name,
                source_flag=source_flag,
                target_flag=target_flag,
            )

        except TranslationNotFound:
            log.tree("Google Translation Not Found", [
                ("Text", text[:50]),
                ("Target", target_lang),
            ], emoji="⚠️")
            return TranslationResult(
                success=False,
                original_text=text,
                translated_text="",
                source_lang=source_lang,
                target_lang=target_lang,
                source_name="",
                target_name="",
                source_flag="",
                target_flag="",
                error="Could not translate this text."
            )

        except Exception as e:
            log.error_tree("Google Translation Failed", e, [
                ("Text", text[:50]),
            ])
            return TranslationResult(
                success=False,
                original_text=text,
                translated_text="",
                source_lang=source_lang,
                target_lang=target_lang,
                source_name="",
                target_name="",
                source_flag="",
                target_flag="",
                error=str(e)
            )

    def _build_ai_prompt(
        self,
        source_name: str,
        target_name: str,
        source_lang: str,
        target_lang: str
    ) -> str:
        """Build a comprehensive system prompt for AI translation."""
        # Base prompt
        prompt_parts = [
            f"You are an expert {source_name} to {target_name} translator.",
            "",
            "TASK: Translate the user's text accurately and naturally.",
            "",
            "CRITICAL RULES:",
            "1. Output ONLY the translation - no explanations, alternatives, or commentary",
            "2. Never say 'Here is the translation' or similar - just give the translated text",
            "3. Preserve the original tone (formal, casual, emotional, humorous)",
            "4. Keep formatting intact (line breaks, punctuation, capitalization style)",
            "5. Preserve emojis exactly as they appear",
            "6. Keep names, brands, and proper nouns unchanged",
            "7. Translate idioms/expressions to natural equivalents, not literally",
        ]

        # Arabic-specific instructions
        if source_lang == "ar" or source_lang == "auto":
            prompt_parts.extend([
                "",
                "ARABIC INPUT HANDLING:",
                "- Recognize Syrian dialect (شامي), Egyptian (مصري), Gulf (خليجي), etc.",
                "- Translate the intended meaning, not literal transliteration",
                "- Common Syrian expressions: شو، كيفك، هلق، منيح، يلا → translate naturally",
            ])

        if target_lang == "ar":
            prompt_parts.extend([
                "",
                "ARABIC OUTPUT:",
                "- Use Modern Standard Arabic (فصحى) for formal text",
                "- For casual/informal input, use natural conversational Arabic",
                "- Ensure proper Arabic grammar and sentence structure",
            ])

        # English-specific
        if target_lang == "en":
            prompt_parts.extend([
                "",
                "ENGLISH OUTPUT:",
                "- Use natural, fluent English that a native speaker would use",
                "- Match the formality level of the source text",
                "- Avoid awkward literal translations",
            ])

        prompt_parts.extend([
            "",
            "If the text is already in the target language, return it unchanged.",
            "If text is ambiguous, choose the most contextually appropriate meaning.",
        ])

        return "\n".join(prompt_parts)

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

        # Build a comprehensive translation prompt
        system_prompt = self._build_ai_prompt(source_name, target_name, source_lang, resolved_target)

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
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": text
                        }
                    ],
                    "temperature": 0.2,
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


    async def check_deepl_usage(self) -> tuple[int, int] | None:
        """Check DeepL API usage. Returns (used, limit) or None if failed."""
        if not config.DEEPL_API_KEY:
            return None

        try:
            async with http_session.session.get(
                "https://api-free.deepl.com/v2/usage",
                headers={
                    "Authorization": f"DeepL-Auth-Key {config.DEEPL_API_KEY}",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                used = data.get("character_count", 0)
                limit = data.get("character_limit", 500000)

                percent = (used / limit * 100) if limit > 0 else 0
                remaining = limit - used

                log.tree("DeepL Usage", [
                    ("Used", f"{used:,} chars"),
                    ("Limit", f"{limit:,} chars"),
                    ("Remaining", f"{remaining:,} chars ({100-percent:.1f}%)"),
                ], emoji="📊")

                return (used, limit)

        except Exception as e:
            log.tree("DeepL Usage Check Failed", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")
            return None


# Global instance
translate_service = TranslateService()
