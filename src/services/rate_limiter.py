"""
SyriaBot - Rate Limiter Service
===============================

Weekly rate limiting for non-privileged users.
Boosters, moderators, and developers get unlimited access.

Limits (per week):
- Convert: 10
- Quote: 15

Resets every Sunday at midnight EST.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from datetime import datetime, timedelta
from threading import Lock
from typing import Optional, Tuple, Set

from src.core.colors import COLOR_GOLD
from src.core.constants import (
    TIMEZONE_EST,
    WEEKLY_LIMITS,
    RATE_LIMIT_ACTION_NAMES,
    RATE_LIMIT_ACTION_EMOJIS,
)
from src.core.logger import log
from src.core.config import config
from src.services.database import db
from src.utils.footer import set_footer

# Aliases for backwards compatibility
EST = TIMEZONE_EST
ACTION_NAMES = RATE_LIMIT_ACTION_NAMES
ACTION_EMOJIS = RATE_LIMIT_ACTION_EMOJIS
COLOR_LIMIT = COLOR_GOLD


# =============================================================================
# Rate Limiter Service
# =============================================================================

class RateLimiter:
    """
    Weekly rate limiting service for non-privileged users.

    Tracks usage per user per action type per week.
    Week resets on Sunday at midnight EST.
    Boosters, moderators, and developers bypass all limits.
    """

    _instance: Optional["RateLimiter"] = None
    _lock: Lock = Lock()

    def __init__(self) -> None:
        """Initialize the rate limiter."""
        self._db_lock = Lock()
        self._exempt_role_ids: Set[int] = set()
        self._initialized = False
        self._load_config()
        self._init_db()

    def _load_config(self) -> None:
        """Load exempt role IDs from config."""
        # Booster role
        if config.BOOSTER_ROLE_ID:
            self._exempt_role_ids.add(config.BOOSTER_ROLE_ID)

        # Mod role
        if config.MOD_ROLE_ID:
            self._exempt_role_ids.add(config.MOD_ROLE_ID)

        log.tree("Rate Limiter Config", [
            ("Booster Role", str(config.BOOSTER_ROLE_ID) if config.BOOSTER_ROLE_ID else "Not set"),
            ("Mod Role", str(config.MOD_ROLE_ID) if config.MOD_ROLE_ID else "Not set"),
            ("Developer", str(config.OWNER_ID) if config.OWNER_ID else "Not set"),
            ("Weekly Limits", f"Convert: {WEEKLY_LIMITS['convert']}, Quote: {WEEKLY_LIMITS['quote']}"),
        ], emoji="⚙️")

    def _init_db(self) -> None:
        """Initialize database table for rate limits."""
        try:
            with db._get_conn() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS rate_limits (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        action_type TEXT NOT NULL,
                        week_start TEXT NOT NULL,
                        usage_count INTEGER DEFAULT 1,
                        last_used TEXT NOT NULL,
                        UNIQUE(user_id, action_type, week_start)
                    )
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_rate_limits_user_week
                    ON rate_limits(user_id, week_start)
                """)

            self._initialized = True
            log.tree("Rate Limiter DB Initialized", [
                ("Table", "rate_limits"),
            ], emoji="✅")

        except Exception as e:
            log.tree("Rate Limiter DB Init Failed", [
                ("Error", str(e)),
            ], emoji="❌")
            self._initialized = False

    @classmethod
    def get_instance(cls) -> "RateLimiter":
        """Get singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # =========================================================================
    # Time Utilities
    # =========================================================================

    def _get_week_start(self) -> str:
        """Get the start of the current week (Sunday midnight EST)."""
        now = datetime.now(EST)
        days_since_sunday = (now.weekday() + 1) % 7
        week_start = now - timedelta(days=days_since_sunday)
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        return week_start.strftime("%Y-%m-%d")

    def _get_next_reset(self) -> datetime:
        """Get the next Sunday midnight EST reset time."""
        now = datetime.now(EST)
        days_until_sunday = (6 - now.weekday()) % 7
        if days_until_sunday == 0 and now.hour >= 0:
            days_until_sunday = 7
        next_sunday = now + timedelta(days=days_until_sunday)
        next_sunday = next_sunday.replace(hour=0, minute=0, second=0, microsecond=0)
        return next_sunday

    # =========================================================================
    # Exemption Checks
    # =========================================================================

    def is_exempt(self, member: discord.Member) -> Tuple[bool, str]:
        """
        Check if a member is exempt from rate limits.

        Returns:
            Tuple of (is_exempt, reason)
        """
        # Check developer
        if config.OWNER_ID and member.id == config.OWNER_ID:
            return True, "Developer"

        # Check if actual booster (premium_since is set when boosting)
        if member.premium_since is not None:
            return True, "Booster"

        # Check exempt roles (booster role, mod role)
        for role in member.roles:
            if role.id in self._exempt_role_ids:
                return True, f"Role: {role.name}"

        return False, "None"

    # =========================================================================
    # Usage Tracking
    # =========================================================================

    def get_usage(self, user_id: int, action_type: str) -> int:
        """Get current usage count for a user and action this week."""
        if not self._initialized:
            return 0

        try:
            with self._db_lock:
                with db._get_conn() as conn:
                    cursor = conn.cursor()
                    week_start = self._get_week_start()

                    cursor.execute("""
                        SELECT usage_count FROM rate_limits
                        WHERE user_id = ? AND action_type = ? AND week_start = ?
                    """, (user_id, action_type, week_start))

                    row = cursor.fetchone()
                    return row[0] if row else 0

        except Exception as e:
            log.tree("Rate Limit Get Usage Failed", [
                ("User ID", str(user_id)),
                ("Action", action_type),
                ("Error", str(e)),
            ], emoji="❌")
            return 0

    def get_remaining(self, user_id: int, action_type: str) -> int:
        """Get remaining uses for a user and action this week."""
        limit = WEEKLY_LIMITS.get(action_type, 0)
        usage = self.get_usage(user_id, action_type)
        return max(0, limit - usage)

    def check_limit(self, member: discord.Member, action_type: str) -> Tuple[bool, int, str]:
        """
        Check if a user can perform an action.

        Returns:
            Tuple of (allowed, remaining_uses, exempt_reason)
            remaining_uses is -1 for exempt users
        """
        # Check exemption first
        is_exempt, exempt_reason = self.is_exempt(member)
        if is_exempt:
            return True, -1, exempt_reason

        # Check remaining uses
        remaining = self.get_remaining(member.id, action_type)
        allowed = remaining > 0

        return allowed, remaining, "None"

    def consume(self, user_id: int, action_type: str) -> bool:
        """Consume one use of an action for a user."""
        if not self._initialized:
            return False

        try:
            with self._db_lock:
                with db._get_conn() as conn:
                    cursor = conn.cursor()
                    week_start = self._get_week_start()
                    now = datetime.now(EST).isoformat()

                    cursor.execute("""
                        INSERT INTO rate_limits (user_id, action_type, week_start, usage_count, last_used)
                        VALUES (?, ?, ?, 1, ?)
                        ON CONFLICT(user_id, action_type, week_start)
                        DO UPDATE SET usage_count = usage_count + 1, last_used = ?
                    """, (user_id, action_type, week_start, now, now))

            return True

        except Exception as e:
            log.tree("Rate Limit Consume Failed", [
                ("User ID", str(user_id)),
                ("Action", action_type),
                ("Error", str(e)),
            ], emoji="❌")
            return False

    # =========================================================================
    # Embed Creation
    # =========================================================================

    def create_limit_embed(self, member: discord.Member, action_type: str) -> discord.Embed:
        """Create an embed for when a user hits their limit."""
        action_name = ACTION_NAMES.get(action_type, action_type)
        action_emoji = ACTION_EMOJIS.get(action_type, "⚠️")
        limit = WEEKLY_LIMITS.get(action_type, 0)

        # Calculate reset time
        next_reset = self._get_next_reset()
        reset_timestamp = int(next_reset.timestamp())

        embed = discord.Embed(
            title=f"{action_emoji} Weekly Limit Reached",
            description=(
                f"You've used all **{limit}** {action_name.lower()} for this week.\n\n"
                f"Your limit resets <t:{reset_timestamp}:F>\n"
                f"That's <t:{reset_timestamp}:R>"
            ),
            color=COLOR_LIMIT
        )

        # Usage field
        embed.add_field(
            name="📊 Your Usage",
            value=f"`{limit}/{limit}` {action_name.lower()} used",
            inline=True
        )

        # Boost encouragement
        embed.add_field(
            name="💎 Want Unlimited Access?",
            value="**Boost the server** to unlock unlimited access to all features!",
            inline=False
        )

        # Booster perks
        embed.add_field(
            name="✨ Booster Perks",
            value=(
                "• Unlimited conversions\n"
                "• Unlimited quotes\n"
                "• Support the community!"
            ),
            inline=False
        )

        set_footer(embed)
        return embed

    # =========================================================================
    # Response Handling
    # =========================================================================

    async def send_limit_response(
        self,
        member: discord.Member,
        action_type: str,
        interaction: Optional[discord.Interaction] = None,
        message: Optional[discord.Message] = None,
    ) -> None:
        """Send limit reached response."""
        import asyncio

        embed = self.create_limit_embed(member, action_type)
        action_name = ACTION_NAMES.get(action_type, action_type)

        # Send via interaction (ephemeral - hidden from others)
        if interaction:
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except discord.HTTPException as e:
                log.tree("Rate Limit Response Failed", [
                    ("User", str(member)),
                    ("Error", str(e)),
                ], emoji="❌")

        # Send via message reply (delete user's message, send temp response)
        elif message:
            try:
                # Delete the user's message (e.g., "convert" or "quote")
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass  # May not have permission

                # Send rate limit embed, then delete after 10 seconds
                response = await message.channel.send(
                    content=member.mention,
                    embed=embed,
                )

                # Schedule deletion after 10 seconds (non-blocking)
                async def delete_after_delay():
                    await asyncio.sleep(10)
                    try:
                        await response.delete()
                    except discord.HTTPException:
                        pass

                asyncio.create_task(delete_after_delay())

            except discord.HTTPException as e:
                log.tree("Rate Limit Reply Failed", [
                    ("User", str(member)),
                    ("Error", str(e)),
                ], emoji="❌")

        log.tree("Rate Limit Reached", [
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
            ("Action", action_name),
            ("Limit", str(WEEKLY_LIMITS.get(action_type, 0))),
            ("Source", "Slash Command" if interaction else "Reply"),
        ], emoji="🚫")

    # =========================================================================
    # Cleanup
    # =========================================================================

    def cleanup_old_records(self, weeks_to_keep: int = 4) -> int:
        """Clean up old rate limit records."""
        if not self._initialized:
            return 0

        try:
            with self._db_lock:
                with db._get_conn() as conn:
                    cursor = conn.cursor()

                    cutoff = datetime.now(EST) - timedelta(weeks=weeks_to_keep)
                    cutoff_str = cutoff.strftime("%Y-%m-%d")

                    cursor.execute("""
                        DELETE FROM rate_limits WHERE week_start < ?
                    """, (cutoff_str,))

                    deleted = cursor.rowcount

            if deleted > 0:
                log.tree("Rate Limit Cleanup", [
                    ("Deleted", str(deleted)),
                    ("Weeks Kept", str(weeks_to_keep)),
                ], emoji="🧹")

            return deleted

        except Exception as e:
            log.tree("Rate Limit Cleanup Failed", [
                ("Error", str(e)),
            ], emoji="❌")
            return 0


# =============================================================================
# Helper Functions
# =============================================================================

def get_rate_limiter() -> RateLimiter:
    """Get the rate limiter singleton instance."""
    return RateLimiter.get_instance()


async def check_rate_limit(
    member: discord.Member,
    action_type: str,
    interaction: Optional[discord.Interaction] = None,
    message: Optional[discord.Message] = None,
) -> bool:
    """
    Check and consume rate limit for an action.

    Args:
        member: Discord member
        action_type: Type of action (convert, quote)
        interaction: Discord interaction (optional)
        message: Discord message (optional, for reply-based commands)

    Returns:
        True if allowed, False if limit reached
    """
    rate_limiter = get_rate_limiter()

    # Check if allowed
    allowed, remaining, exempt_reason = rate_limiter.check_limit(member, action_type)

    if not allowed:
        await rate_limiter.send_limit_response(
            member=member,
            action_type=action_type,
            interaction=interaction,
            message=message,
        )
        return False

    # Consume one use (only if not exempt)
    if remaining != -1:
        rate_limiter.consume(member.id, action_type)

    return True


__all__ = [
    "RateLimiter",
    "get_rate_limiter",
    "check_rate_limit",
    "WEEKLY_LIMITS",
    "ACTION_NAMES",
]
