"""
SyriaBot - Presence Handler
===========================

Bot presence with rotating status and hourly promo.

Features:
- Rotating status messages (XP/leveling stats)
- Hourly promotional presence window
- Graceful start/stop lifecycle

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

import discord
from discord.ext import commands

from src.core.logger import logger
from src.core.constants import (
    PRESENCE_UPDATE_INTERVAL,
    PROMO_DURATION_MINUTES,
    PROMO_TEXT,
    TIMEZONE_EST,
)
from src.services.database import db

if TYPE_CHECKING:
    from discord import Client


# =============================================================================
# Constants
# =============================================================================

DEFAULT_PROMO_DURATION_MINUTES = 10
DEFAULT_UPDATE_INTERVAL = 60


# =============================================================================
# Base Presence Handler
# =============================================================================

class BasePresenceHandler(ABC):
    """
    Base class for Discord presence management.

    DESIGN:
        Manages two concurrent tasks:
        - Rotation loop: Cycles through status messages at configurable interval
        - Promo loop: Shows promotional text at the top of each hour
        Subclasses implement get_status_messages() and get_promo_text().
    """

    def __init__(
        self,
        bot: "Client",
        *,
        update_interval: int = DEFAULT_UPDATE_INTERVAL,
        promo_duration_minutes: int = DEFAULT_PROMO_DURATION_MINUTES,
    ) -> None:
        """
        Initialize the presence handler.

        Args:
            bot: Discord client/bot instance.
            update_interval: Seconds between status rotations.
            promo_duration_minutes: How long to show promo at top of each hour.
        """
        self.bot = bot
        self.update_interval = update_interval
        self.promo_duration_minutes = promo_duration_minutes

        # Background tasks
        self._rotation_task: Optional[asyncio.Task] = None
        self._promo_task: Optional[asyncio.Task] = None

        # State tracking
        self._current_index: int = 0
        self._is_promo_active: bool = False
        self._running: bool = False

    # =========================================================================
    # Abstract Methods
    # =========================================================================

    @abstractmethod
    def get_status_messages(self) -> List[str]:
        """Get list of status messages to rotate through."""
        pass

    @abstractmethod
    def get_promo_text(self) -> str:
        """Get the promotional text to display at top of each hour."""
        pass

    @abstractmethod
    def get_timezone(self) -> "ZoneInfo":
        """Get the timezone for promo scheduling."""
        pass

    # =========================================================================
    # Optional Hooks
    # =========================================================================

    def on_rotation_start(self) -> None:
        """Called when rotation loop starts."""
        pass

    def on_promo_start(self) -> None:
        """Called when promo loop starts."""
        pass

    def on_promo_activated(self) -> None:
        """Called when promo presence is shown."""
        pass

    def on_promo_ended(self) -> None:
        """Called when promo ends and rotation resumes."""
        pass

    def on_handler_ready(self) -> None:
        """Called when handler is fully started."""
        pass

    def on_handler_stopped(self) -> None:
        """Called when handler is stopped."""
        pass

    def on_error(self, context: str, error: Exception) -> None:
        """Called on errors."""
        pass

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """Start the presence handler tasks."""
        if self._running:
            return

        self._running = True
        self._rotation_task = asyncio.create_task(self._rotation_loop())
        self._promo_task = asyncio.create_task(self._promo_loop())
        self.on_handler_ready()

    async def stop(self) -> None:
        """Stop the presence handler tasks."""
        self._running = False

        if self._rotation_task:
            self._rotation_task.cancel()
            try:
                await self._rotation_task
            except asyncio.CancelledError:
                pass
            self._rotation_task = None

        if self._promo_task:
            self._promo_task.cancel()
            try:
                await self._promo_task
            except asyncio.CancelledError:
                pass
            self._promo_task = None

        self.on_handler_stopped()

    # =========================================================================
    # Rotation Loop
    # =========================================================================

    async def _rotation_loop(self) -> None:
        """Background task that rotates presence every interval."""
        await self.bot.wait_until_ready()
        self.on_rotation_start()

        while self._running:
            try:
                await asyncio.sleep(self.update_interval)

                if self._is_promo_active:
                    continue

                await self._update_rotating_presence()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.on_error("Rotation Loop", e)
                await asyncio.sleep(self.update_interval)

    async def _update_rotating_presence(self) -> None:
        """Update presence with rotating status messages."""
        if self._is_promo_active:
            return

        try:
            messages = self.get_status_messages()

            if not messages:
                status_text = self.get_promo_text()
            else:
                self._current_index = self._current_index % len(messages)
                status_text = messages[self._current_index]
                self._current_index += 1

            await self.bot.change_presence(
                activity=discord.CustomActivity(name=status_text)
            )

        except Exception as e:
            self.on_error("Presence Update", e)

    # =========================================================================
    # Promo Loop
    # =========================================================================

    async def _promo_loop(self) -> None:
        """Background task that shows promo at the top of each hour."""
        await self.bot.wait_until_ready()
        self.on_promo_start()

        while self._running:
            try:
                now = datetime.now(self.get_timezone())
                minutes_until_hour = 60 - now.minute
                seconds_until_hour = (minutes_until_hour * 60) - now.second

                if seconds_until_hour > 0:
                    await asyncio.sleep(seconds_until_hour)

                await self._show_promo_presence()
                await asyncio.sleep(self.promo_duration_minutes * 60)
                await self._restore_normal_presence()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._is_promo_active = False
                self.on_error("Promo Loop", e)
                await asyncio.sleep(60)

    async def _show_promo_presence(self) -> None:
        """Show promotional presence."""
        try:
            self._is_promo_active = True
            await self.bot.change_presence(
                activity=discord.CustomActivity(name=self.get_promo_text())
            )
            self.on_promo_activated()
        except Exception as e:
            self.on_error("Show Promo", e)
            self._is_promo_active = False

    async def _restore_normal_presence(self) -> None:
        """Restore normal presence after promo ends."""
        try:
            self._is_promo_active = False
            await self._update_rotating_presence()
            self.on_promo_ended()
        except Exception as e:
            self.on_error("Restore Presence", e)
            self._is_promo_active = False

    # =========================================================================
    # Public API
    # =========================================================================

    @property
    def is_promo_active(self) -> bool:
        """Check if promo is currently showing."""
        return self._is_promo_active

    async def force_update(self) -> None:
        """Force an immediate presence update."""
        if not self._is_promo_active:
            await self._update_rotating_presence()


# =============================================================================
# SyriaBot Presence Handler
# =============================================================================

class PresenceHandler(BasePresenceHandler):
    """
    SyriaBot presence handler with XP/leveling stats.

    DESIGN:
        Rotates through XP statistics (total XP, messages, voice hours).
        Shows discord.gg/syria promo at the top of each hour.
        Stats pulled from database on each rotation cycle.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the SyriaBot presence handler.

        Args:
            bot: Main bot instance for Discord API access.
        """
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
            stats = db.get_xp_stats()
            total_users = stats.get("total_users", 0)
            total_xp = stats.get("total_xp", 0)
            total_messages = stats.get("total_messages", 0)
            total_voice = stats.get("total_voice_minutes", 0)

            voice_hours = total_voice // 60

            if total_users > 0:
                messages.append(f"🏆 {self._format_number(total_users)} members ranked")

            if total_xp > 0:
                messages.append(f"⭐ {self._format_number(total_xp)} total XP earned")

            if total_messages > 0:
                messages.append(f"💬 {self._format_number(total_messages)} messages sent")

            if voice_hours > 0:
                messages.append(f"🎙️ {self._format_number(voice_hours)}h in voice")

        except Exception as e:
            logger.error_tree("Presence Stats Error", e)

        if not messages:
            messages = ["🇸🇾 discord.gg/syria"]

        return messages

    def get_promo_text(self) -> str:
        """Return SyriaBot promo text."""
        return PROMO_TEXT

    def get_timezone(self) -> "ZoneInfo":
        """Return EST timezone for promo scheduling."""
        return TIMEZONE_EST

    # =========================================================================
    # Logging Hooks
    # =========================================================================

    def on_rotation_start(self) -> None:
        logger.tree("Presence Rotation Started", [
            ("Interval", f"{self.update_interval}s"),
        ], emoji="🔄")

    def on_promo_start(self) -> None:
        logger.tree("Promo Loop Started", [
            ("Duration", f"{self.promo_duration_minutes} min/hour"),
            ("Text", PROMO_TEXT),
        ], emoji="📢")

    def on_promo_activated(self) -> None:
        logger.tree("Promo Active", [
            ("Text", PROMO_TEXT),
            ("Duration", f"{self.promo_duration_minutes} min"),
        ], emoji="📢")

    def on_promo_ended(self) -> None:
        logger.tree("Promo Ended", [
            ("Resuming", "Normal rotation"),
        ], emoji="🔄")

    def on_handler_ready(self) -> None:
        logger.tree("Presence Handler Ready", [
            ("Rotation", f"Every {self.update_interval}s"),
            ("Promo", f"{self.promo_duration_minutes} min/hour"),
        ], emoji="✅")

    def on_handler_stopped(self) -> None:
        logger.tree("Presence Handler Stopped", [
            ("Status", "Tasks cancelled"),
        ], emoji="🛑")

    def on_error(self, context: str, error: Exception) -> None:
        logger.error_tree(f"{context} Error", error)

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


# =============================================================================
# Module Export
# =============================================================================

__all__ = [
    "PresenceHandler",
    "BasePresenceHandler",
]
