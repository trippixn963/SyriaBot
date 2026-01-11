"""
SyriaBot - FAQ Auto-Responder
=============================

Watches messages for common questions and auto-replies with FAQ.
Includes fuzzy matching to catch typos like "tempvocie" or "tenpvoice".

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import re
import time
import discord
from typing import Optional

from src.core.config import config
from src.core.logger import log
from src.core.colors import COLOR_SYRIA_GREEN
from src.utils.footer import set_footer
from src.services.faq import FAQ_DATA, faq_analytics, FAQView


# =============================================================================
# Cooldowns
# =============================================================================

# Per-user cooldown: {user_id: last_faq_time}
_user_cooldowns: dict[int, float] = {}
USER_COOLDOWN = 300  # 5 minutes per user

# Per-channel cooldown for same topic: {(channel_id, topic): last_time}
_channel_topic_cooldowns: dict[tuple[int, str], float] = {}
CHANNEL_TOPIC_COOLDOWN = 120  # 2 minutes for same topic in same channel

# Max tracked entries (memory management)
MAX_COOLDOWN_ENTRIES = 500

# Channels where auto-FAQ is disabled (manual /faq still works)
FAQ_IGNORED_CHANNELS = {
    1457000381702738105,
    1459144517449158719,
}


# =============================================================================
# Fuzzy Matching
# =============================================================================

# Keywords to fuzzy match -> correct spelling
FUZZY_KEYWORDS = {
    "tempvoice": ["tempvoice", "temp voice", "temporary voice"],
    "voice": ["voice", "vc"],
    "channel": ["channel"],
    "level": ["level", "lvl"],
    "rank": ["rank"],
    "xp": ["xp", "exp"],
    "role": ["role", "roles"],
    "casino": ["casino"],
    "gamble": ["gamble", "gambling"],
    "economy": ["economy"],
    "coin": ["coin", "coins", "money"],
    "confess": ["confess", "confession", "confessions"],
    "report": ["report"],
    "invite": ["invite", "invitation"],
    "partner": ["partner", "partnership"],
    "giveaway": ["giveaway", "giveaways"],
}


def _levenshtein(s1: str, s2: str) -> int:
    """Calculate Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)

    if len(s2) == 0:
        return len(s1)

    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def _fuzzy_correct(text: str) -> str:
    """
    Correct typos in text using fuzzy matching.

    Replaces misspelled keywords with correct versions.
    """
    words = text.lower().split()
    corrected = []

    for word in words:
        # Skip short words (less prone to meaningful typos)
        if len(word) < 4:
            corrected.append(word)
            continue

        best_match = word
        best_distance = float('inf')

        # Check against all fuzzy keywords
        for correct, variants in FUZZY_KEYWORDS.items():
            for variant in variants:
                # Skip if lengths differ too much
                if abs(len(word) - len(variant)) > 2:
                    continue

                distance = _levenshtein(word, variant)

                # Threshold: 1 edit for short words, 2 for longer
                threshold = 1 if len(variant) <= 5 else 2

                if distance <= threshold and distance < best_distance:
                    best_distance = distance
                    best_match = correct

        corrected.append(best_match)

    return " ".join(corrected)


# =============================================================================
# FAQ Patterns (for auto-detection)
# =============================================================================

FAQ_PATTERNS = {
    "xp": [
        r"how.*(xp|level|rank)",
        r"how.*level.*up",
        r"how.*get.*xp",
        r"what.*xp",
        r"xp.*work",
        r"leveling.*system",
        r"rank.*work",
    ],
    "roles": [
        r"how.*(get|buy|earn).*role",
        r"how.*role.*work",
        r"where.*get.*role",
        r"can.*i.*get.*role",
        r"role.*shop",
        r"buy.*role",
        r"custom.*role",
    ],
    "tempvoice": [
        r"how.*(create|make).*vc",
        r"how.*(create|make).*voice",
        r"how.*temp.*voice",
        r"how.*private.*vc",
        r"custom.*voice.*channel",
        r"tempvoice",
        r"how.*own.*channel",
    ],
    "report": [
        r"how.*(report|ban)",
        r"where.*report",
        r"report.*someone",
        r"how.*tell.*mod",
        r"someone.*breaking.*rule",
    ],
    "confess": [
        r"how.*(confess|confession)",
        r"where.*(confess|confession)",
        r"anonymous.*message",
        r"send.*anonymous",
    ],
    "economy": [
        r"how.*(earn|get).*coin",
        r"how.*economy",
        r"how.*money.*work",
        r"where.*check.*balance",
        r"how.*get.*rich",
        r"coin.*system",
    ],
    "casino": [
        r"how.*casino",
        r"how.*gambl",
        r"where.*casino",
        r"how.*play.*(roulette|blackjack|slot)",
        r"casino.*game",
    ],
    "invite": [
        r"(server|discord).*(link|invite)",
        r"invite.*link",
        r"how.*invite.*friend",
        r"can.*i.*invite",
    ],
    "partnership": [
        r"partner(ship)?",
        r"how.*(partner|collab)",
        r"can.*(partner|collab)",
        r"want.*partner",
        r"looking.*partner",
        r"server.*partner",
    ],
}


# =============================================================================
# FAQ Handler
# =============================================================================

class FAQAutoResponder:
    """Watches messages and auto-replies with FAQ when questions are detected."""

    def __init__(self):
        # Compile regex patterns for efficiency
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}
        for topic, patterns in FAQ_PATTERNS.items():
            self._compiled_patterns[topic] = [
                re.compile(pattern, re.IGNORECASE)
                for pattern in patterns
            ]

    def _check_cooldowns(self, user_id: int, channel_id: int, topic: str) -> bool:
        """Check if we should respond (cooldowns not active)."""
        now = time.time()

        # Check user cooldown
        if user_id in _user_cooldowns:
            if now - _user_cooldowns[user_id] < USER_COOLDOWN:
                return False

        # Check channel+topic cooldown
        key = (channel_id, topic)
        if key in _channel_topic_cooldowns:
            if now - _channel_topic_cooldowns[key] < CHANNEL_TOPIC_COOLDOWN:
                return False

        return True

    def _update_cooldowns(self, user_id: int, channel_id: int, topic: str) -> None:
        """Update cooldowns after sending FAQ."""
        now = time.time()
        _user_cooldowns[user_id] = now
        _channel_topic_cooldowns[(channel_id, topic)] = now

        # Memory cleanup - evict old entries
        if len(_user_cooldowns) > MAX_COOLDOWN_ENTRIES:
            sorted_entries = sorted(_user_cooldowns.items(), key=lambda x: x[1])
            for uid, _ in sorted_entries[:MAX_COOLDOWN_ENTRIES // 5]:
                del _user_cooldowns[uid]

        if len(_channel_topic_cooldowns) > MAX_COOLDOWN_ENTRIES:
            sorted_entries = sorted(_channel_topic_cooldowns.items(), key=lambda x: x[1])
            for key, _ in sorted_entries[:MAX_COOLDOWN_ENTRIES // 5]:
                del _channel_topic_cooldowns[key]

    def _detect_question(self, content: str) -> bool:
        """Check if message looks like a question."""
        content_lower = content.lower()

        # Must have question indicators
        question_starters = ["how", "what", "where", "can i", "how do", "how to", "why"]
        has_question_word = any(content_lower.startswith(w) or f" {w}" in content_lower for w in question_starters)
        has_question_mark = "?" in content

        return has_question_word or has_question_mark

    def _match_topic(self, content: str) -> Optional[str]:
        """Match content to a FAQ topic with fuzzy typo correction."""
        # First try exact match
        for topic, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(content):
                    return topic

        # If no match, try with fuzzy corrected content
        corrected = _fuzzy_correct(content)
        if corrected != content.lower():
            for topic, patterns in self._compiled_patterns.items():
                for pattern in patterns:
                    if pattern.search(corrected):
                        return topic

        return None

    async def handle(self, message: discord.Message) -> bool:
        """
        Check message for FAQ questions and respond if matched.

        Returns True if FAQ was sent, False otherwise.
        """
        # Only in main guild
        if not message.guild or message.guild.id != config.GUILD_ID:
            return False

        # Skip ignored channels
        if message.channel.id in FAQ_IGNORED_CHANNELS:
            return False

        content = message.content.strip()

        # Skip short messages
        if len(content) < 10:
            return False

        # Must look like a question
        if not self._detect_question(content):
            return False

        # Try to match a topic (with fuzzy correction for typos)
        topic = self._match_topic(content)
        if not topic:
            return False

        # Check if fuzzy matching was used
        corrected = _fuzzy_correct(content)
        was_fuzzy = corrected != content.lower() and not any(
            p.search(content) for patterns in self._compiled_patterns.values() for p in patterns
        )

        # Check if topic exists in FAQ_DATA
        if topic not in FAQ_DATA:
            return False

        # Check cooldowns
        if not self._check_cooldowns(message.author.id, message.channel.id, topic):
            log.tree("FAQ Cooldown Active", [
                ("User", f"{message.author.name}"),
                ("Topic", topic),
            ], emoji="⏳")
            return False

        # Get FAQ data
        faq = FAQ_DATA[topic]

        # Create embed (default English)
        embed = discord.Embed(
            title=faq["title"]["en"],
            description=faq["description"]["en"],
            color=COLOR_SYRIA_GREEN,
        )
        set_footer(embed)

        # Create view with buttons
        view = FAQView(topic=topic, current_lang="en")

        try:
            sent_msg = await message.reply(embed=embed, view=view, mention_author=False)
            view.message = sent_msg

            # Update cooldowns
            self._update_cooldowns(message.author.id, message.channel.id, topic)

            # Record analytics
            faq_analytics.record_trigger(topic)

            log_entries = [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("Topic", topic),
                ("Channel", message.channel.name if hasattr(message.channel, 'name') else str(message.channel.id)),
                ("Trigger", content[:50] + "..." if len(content) > 50 else content),
            ]
            if was_fuzzy:
                log_entries.append(("Fuzzy Match", "Yes"))
            log.tree("FAQ Auto-Sent", log_entries, emoji="📋")

            return True

        except discord.Forbidden:
            log.tree("FAQ Send Failed", [
                ("Reason", "Missing permissions"),
                ("Channel", str(message.channel.id)),
            ], emoji="❌")
            return False
        except Exception as e:
            log.tree("FAQ Send Error", [
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False


# Global instance
faq_handler = FAQAutoResponder()
