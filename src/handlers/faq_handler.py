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
        r"how\s+(do\s+)?(i|we|you)\s+(get|earn|gain)\s+(xp|level|rank)",
        r"how\s+(does|do)\s+(the\s+)?(xp|leveling|ranking)\s+(system\s+)?work",
        r"how\s+(do\s+)?(i|you)\s+level\s+up",
        r"what\s+is\s+(the\s+)?(xp|leveling)\s+system",
        r"how\s+to\s+(get|earn)\s+(xp|level)",
    ],
    "roles": [
        r"how\s+(do\s+)?(i|we|you)\s+(get|buy|earn|obtain)\s+(a\s+)?(custom\s+)?role",
        r"how\s+(does|do)\s+(the\s+)?role(s)?\s+(system\s+)?work",
        r"where\s+(can\s+)?(i|we)\s+(get|buy)\s+(a\s+)?role",
        r"how\s+to\s+(get|buy|earn)\s+(a\s+)?role",
    ],
    "tempvoice": [
        r"how\s+(do\s+)?(i|we|you)\s+(create|make)\s+(a\s+)?(private\s+)?(vc|voice(\s+channel)?)",
        r"how\s+(does|do)\s+(the\s+)?temp\s*voice\s+work",
        r"how\s+to\s+(create|make|get)\s+(a\s+)?(my\s+)?(own\s+)?(private\s+)?(vc|voice(\s+channel)?)",
        r"what\s+is\s+temp\s*voice",
    ],
    "report": [
        r"how\s+(do\s+)?(i|we)\s+report\s+(a\s+)?(someone|user|person|member)",
        r"where\s+(can\s+)?(i|we)\s+report\s+(someone|a\s+user)",
        r"how\s+to\s+report\s+(someone|a\s+user|a\s+person)",
        r"how\s+(do\s+)?(i|we)\s+(contact|tell|reach)\s+(the\s+)?(mods?|staff|admin)",
    ],
    "confess": [
        r"how\s+(do\s+)?(i|we|you)\s+(send|make|post)\s+(a\s+)?(an?\s+)?(anonymous\s+)?(confess(ion)?|message)",
        r"where\s+(can\s+)?(i|we)\s+(confess|send\s+confessions?)",
        r"how\s+(does|do)\s+(the\s+)?confess(ion)?(s)?\s+(system\s+)?work",
        r"how\s+to\s+(confess|send\s+a\s+confession)",
    ],
    "economy": [
        r"how\s+(do\s+)?(i|we|you)\s+(earn|get|make)\s+(server\s+)?(coins?|money|currency)",
        r"how\s+(does|do)\s+(the\s+)?(economy|coin|money)\s+(system\s+)?work",
        r"where\s+(can\s+)?(i|we)\s+(check|see)\s+(my\s+)?balance",
        r"how\s+to\s+(earn|get|make)\s+(coins?|money)",
    ],
    "casino": [
        r"how\s+(do\s+)?(i|we|you)\s+(use|play|access)\s+(the\s+)?casino",
        r"how\s+(does|do)\s+(the\s+)?casino\s+(games?\s+)?work",
        r"where\s+is\s+(the\s+)?casino",
        r"how\s+to\s+play\s+(roulette|blackjack|slots?)",
    ],
    "invite": [
        r"what\s+is\s+(the\s+)?(server\s+)?(invite\s+)?(link|url)",
        r"(can\s+)?(i|we)\s+(have|get)\s+(the\s+)?(server\s+)?invite(\s+link)?",
        r"(share|send)\s+(me\s+)?(the\s+)?(server\s+)?invite(\s+link)?",
    ],
    "partnership": [
        r"how\s+(do\s+)?(i|we)\s+(request|apply\s+for|get)\s+(a\s+)?partnership",
        r"how\s+(does|do)\s+(the\s+)?partnership(s)?\s+work",
        r"(can|how\s+to)\s+partner\s+with\s+(this\s+)?(server|you)",
        r"where\s+(do\s+)?(i|we)\s+(apply|request)\s+(for\s+)?(a\s+)?partnership",
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
        """Check if message looks like a genuine question about server features."""
        content_lower = content.lower().strip()

        # Must START with a question word (not just contain it somewhere)
        question_starters = ["how ", "what ", "where ", "can i ", "can we ", "how do ", "how to ", "how does "]
        starts_with_question = any(content_lower.startswith(w) for w in question_starters)

        # Or have a question mark AND start with a question-like structure
        has_question_mark = content.endswith("?")

        # Reject if it's clearly just a statement or conversation
        # (contains multiple sentences, starts with "i ", etc.)
        if content_lower.startswith(("i ", "my ", "im ", "i'm ", "lol", "lmao", "haha", "bruh")):
            return False

        return starts_with_question or (has_question_mark and len(content) < 100)

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

        # Skip short messages (need enough context to be a real question)
        if len(content) < 15:
            return False

        # Skip long messages (likely conversations, not simple questions)
        if len(content) > 200:
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
