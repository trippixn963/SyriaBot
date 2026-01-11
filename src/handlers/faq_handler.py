"""
SyriaBot - FAQ Auto-Responder
=============================

Watches messages for common questions and auto-replies with FAQ.

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


# =============================================================================
# FAQ Patterns
# =============================================================================

# Each pattern: (topic, keywords/phrases to match, question indicators)
FAQ_PATTERNS = {
    "xp": {
        "keywords": [
            r"how.*(xp|level|rank)",
            r"how.*level.*up",
            r"how.*get.*xp",
            r"what.*xp",
            r"xp.*work",
            r"leveling.*system",
            r"rank.*work",
        ],
        "title": "📊 How XP & Leveling Works",
        "description": """**Earning XP:**
• **Messages:** 8-12 XP per message (60 second cooldown)
• **Voice:** 3 XP per minute (must have 2+ people, not deafened)
• **Boosters:** <@&1230147693490471023> get 2x XP multiplier

**Level Rewards:**
• Level 1 → Connect to voice channels
• Level 5 → Attach files & embed links
• Level 10 → Use external emojis
• Level 20 → Use external stickers
• Level 30 → Change nickname

Check your rank with `/rank`""",
    },
    "roles": {
        "keywords": [
            r"how.*(get|buy|earn).*role",
            r"how.*role.*work",
            r"where.*get.*role",
            r"can.*i.*get.*role",
            r"role.*shop",
            r"buy.*role",
            r"custom.*role",
        ],
        "title": "🎭 How to Get Roles",
        "description": """**Auto Roles:**
• You get <@&1236824194722041876> automatically when you join
• Level roles are given automatically as you level up

**Self-Assign Roles:**
• Go to <id:customize> to pick your roles
• Choose colors, pronouns, notifications, etc.

**Purchasable Roles (Economy):**
• Earn coins by chatting, playing games, and being active
• Check your balance in <#1459658497879707883>
• Buy custom roles in <#1459644341361447181>

**Special Roles:**
• <@&1230147693490471023> roles → boost the server
• Staff roles → given by admins only""",
    },
    "tempvoice": {
        "keywords": [
            r"how.*(create|make).*vc",
            r"how.*(create|make).*voice",
            r"how.*temp.*voice",
            r"how.*private.*vc",
            r"custom.*voice.*channel",
            r"tempvoice",
            r"how.*own.*channel",
        ],
        "title": "🎤 TempVoice (Custom Voice Channels)",
        "description": """**How to Create:**
1. Join <#1455684848977969399>
2. You'll be moved to your own private channel
3. Use the control panel to manage it

**What You Can Do:**
• Rename your channel
• Set user limit
• Lock/unlock the channel
• Kick/ban users from your channel
• Transfer ownership

Your channel is deleted when everyone leaves.""",
    },
    "report": {
        "keywords": [
            r"how.*(report|ban)",
            r"where.*report",
            r"report.*someone",
            r"how.*tell.*mod",
            r"someone.*breaking.*rule",
        ],
        "title": "📥 How to Report Someone",
        "description": """**To report a rule violation:**
1. Go to <#1406750411779604561>
2. Create a ticket with details
3. Include screenshots/evidence if possible

**Do NOT:**
• Ping staff in public channels
• Report in general chat
• Mini-mod or confront the person yourself

Staff will handle it privately.""",
    },
    "confess": {
        "keywords": [
            r"how.*(confess|confession)",
            r"where.*(confess|confession)",
            r"anonymous.*message",
            r"send.*anonymous",
        ],
        "title": "🤫 Anonymous Confessions",
        "description": """**How to Confess:**
1. Use `/confess` command anywhere
2. Type your confession (text only)
3. It will be posted in <#1459123706189058110>

**Rules:**
• No hate speech or harassment
• No doxxing or personal info
• No NSFW content

Confessions can be traced by staff if rules are broken.""",
    },
    "economy": {
        "keywords": [
            r"how.*(earn|get).*coin",
            r"how.*economy",
            r"how.*money.*work",
            r"where.*check.*balance",
            r"how.*get.*rich",
            r"coin.*system",
        ],
        "title": "💰 Economy System",
        "description": """**How to Earn Coins:**
• Chat in the server (passive income)
• Play casino games (roulette, blackjack, slots)
• Win minigames and events
• Daily rewards with `/daily`

**Check Balance:**
• Use commands in <#1459658497879707883>

**Spending:**
• Buy roles in <#1459644341361447181>
• Gamble in the casino""",
    },
    "casino": {
        "keywords": [
            r"how.*casino",
            r"how.*gambl",
            r"where.*casino",
            r"how.*play.*(roulette|blackjack|slot)",
            r"casino.*game",
        ],
        "title": "🎰 Casino Games",
        "description": """**Available Games:**
• 🎡 **Roulette** - Bet on numbers, colors, or ranges
• 🃏 **Blackjack** - Classic 21 card game
• 🎰 **Slots** - Spin to win

**How to Play:**
1. Go to the Casino forum
2. Find the game you want to play
3. Use the bot commands in that post

**Warning:** Only bet what you're willing to lose!""",
    },
    "invite": {
        "keywords": [
            r"(server|discord).*(link|invite)",
            r"invite.*link",
            r"how.*invite.*friend",
            r"can.*i.*invite",
        ],
        "title": "🔗 Server Invite",
        "description": """**Permanent Invite Link:**
https://discord.gg/syria

Feel free to share this with friends!

**Note:** Advertising other servers in DMs is against the rules.""",
    },
    "partnership": {
        "keywords": [
            r"partner(ship)?",
            r"how.*(partner|collab)",
            r"can.*(partner|collab)",
            r"want.*partner",
            r"looking.*partner",
            r"server.*partner",
        ],
        "title": "🤝 Partnership Requests",
        "description": """**Want to partner with us?**

1. Go to <#1406750411779604561>
2. Open a **Partnership** ticket
3. Include your server's invite link and member count
4. Wait for a staff member to review

**Requirements:**
• Your server must have a reasonable member count
• No NSFW or rule-breaking content
• Must be an active, established community

**Do NOT:**
• DM staff or admins directly
• Advertise in public channels
• Spam partnership requests""",
    },
}


# =============================================================================
# FAQ Handler
# =============================================================================

class FAQAutoResponder:
    """Watches messages and auto-replies with FAQ when questions are detected."""

    def __init__(self):
        # Compile regex patterns for efficiency
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}
        for topic, data in FAQ_PATTERNS.items():
            self._compiled_patterns[topic] = [
                re.compile(pattern, re.IGNORECASE)
                for pattern in data["keywords"]
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
            # Remove oldest 20%
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
        """Match content to a FAQ topic."""
        for topic, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(content):
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

        content = message.content.strip()

        # Skip short messages
        if len(content) < 10:
            return False

        # Must look like a question
        if not self._detect_question(content):
            return False

        # Try to match a topic
        topic = self._match_topic(content)
        if not topic:
            return False

        # Check cooldowns
        if not self._check_cooldowns(message.author.id, message.channel.id, topic):
            log.tree("FAQ Cooldown Active", [
                ("User", f"{message.author.name}"),
                ("Topic", topic),
            ], emoji="⏳")
            return False

        # Get FAQ data
        faq = FAQ_PATTERNS[topic]

        # Create embed
        embed = discord.Embed(
            title=faq["title"],
            description=faq["description"],
            color=COLOR_SYRIA_GREEN,
        )
        embed.set_footer(text="Syria • discord.gg/syria")

        try:
            await message.reply(embed=embed, mention_author=False)

            # Update cooldowns
            self._update_cooldowns(message.author.id, message.channel.id, topic)

            log.tree("FAQ Auto-Sent", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("Topic", topic),
                ("Channel", message.channel.name if hasattr(message.channel, 'name') else str(message.channel.id)),
                ("Trigger", content[:50] + "..." if len(content) > 50 else content),
            ], emoji="📋")

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
