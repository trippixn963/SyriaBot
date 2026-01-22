"""
SyriaBot - Presence Handler
===========================

Wrapper around unified presence system with SyriaBot-specific stats.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import Optional, List

from discord.ext import commands

from src.core.logger import log
from src.core.constants import (
    PRESENCE_UPDATE_INTERVAL,
    PROMO_DURATION_MINUTES,
    PROMO_TEXT,
    TIMEZONE_EST,
)
from src.services.database import db

# Import from shared unified presence system
from shared.services.presence import BasePresenceHandler


# =============================================================================
# SyriaBot Presence Handler
# =============================================================================

class PresenceHandler(BasePresenceHandler):
    """Presence handler configured for SyriaBot with XP/leveling stats."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(
            bot,
            update_interval=PRESENCE_UPDATE_INTERVAL,
            promo_duration_minutes=PROMO_DURATION_MINUTES,
        )

    # =========================================================================
    # Required Implementations
    # =========================================================================

    def get_status_messages(self) -> List[str]:
        """Get XP stats for presence rotation."""
        messages = []

        try:
            # Get XP stats from database
            stats = db.get_xp_stats()
            total_users = stats.get("total_users", 0)
            total_xp = stats.get("total_xp", 0)
            total_messages = stats.get("total_messages", 0)
            total_voice = stats.get("total_voice_minutes", 0)

            # Format voice time
            voice_hours = total_voice // 60

            # Build status messages with all-time stats only
            if total_users > 0:
                messages.append(f"🏆 {self._format_number(total_users)} members ranked")

            if total_xp > 0:
                messages.append(f"⭐ {self._format_number(total_xp)} total XP earned")

            if total_messages > 0:
                messages.append(f"💬 {self._format_number(total_messages)} messages sent")

            if voice_hours > 0:
                messages.append(f"🎙️ {self._format_number(voice_hours)}h in voice")

        except Exception as e:
            log.error_tree("Presence Stats Error", e)

        # Fallback if no stats available
        if not messages:
            messages = ["🇸🇾 discord.gg/syria"]

        return messages

    def get_promo_text(self) -> str:
        """Return SyriaBot promo text."""
        return PROMO_TEXT

    def get_timezone(self):
        """Return EST timezone for promo scheduling."""
        return TIMEZONE_EST

    # =========================================================================
    # Logging Hooks
    # =========================================================================

    def on_rotation_start(self) -> None:
        log.tree("Presence Rotation Started", [
            ("Interval", f"{self.update_interval}s"),
        ], emoji="🔄")

    def on_promo_start(self) -> None:
        log.tree("Promo Loop Started", [
            ("Duration", f"{self.promo_duration_minutes} min/hour"),
            ("Text", PROMO_TEXT),
        ], emoji="📢")

    def on_promo_activated(self) -> None:
        log.tree("Promo Active", [
            ("Text", PROMO_TEXT),
            ("Duration", f"{self.promo_duration_minutes} min"),
        ], emoji="📢")

    def on_promo_ended(self) -> None:
        log.tree("Promo Ended", [
            ("Resuming", "Normal rotation"),
        ], emoji="🔄")

    def on_handler_ready(self) -> None:
        log.tree("Presence Handler Ready", [
            ("Rotation", f"Every {self.update_interval}s"),
            ("Promo", f"{self.promo_duration_minutes} min/hour"),
        ], emoji="✅")

    def on_handler_stopped(self) -> None:
        log.tree("Presence Handler Stopped", [
            ("Status", "Tasks cancelled"),
        ], emoji="🛑")

    def on_error(self, context: str, error: Exception) -> None:
        log.error_tree(f"{context} Error", error)

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _format_number(n: int) -> str:
        """Format a number with K/M abbreviations."""
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        elif n >= 1_000:
            return f"{n/1_000:.1f}K"
        return str(n)

    # =========================================================================
    # Compatibility Alias
    # =========================================================================

    async def setup(self) -> None:
        """Alias for start() for backwards compatibility."""
        await self.start()
