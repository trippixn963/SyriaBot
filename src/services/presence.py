"""
SyriaBot - Presence Handler
===========================

Manages rotating Discord presence with stats and hourly promo.
Modeled after AzabBot's presence system.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from datetime import datetime
from typing import Optional, List, Callable

import discord
from discord.ext import commands

from src.core.logger import log
from src.core.constants import (
    PRESENCE_UPDATE_INTERVAL,
    PROMO_DURATION_MINUTES,
    PROMO_TEXT,
    TIMEZONE_EST,
)
from src.services.database import db


class PresenceHandler:
    """Handles rotating presence and hourly promo messages."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the presence handler.

        Args:
            bot: The Discord bot instance.
        """
        self.bot = bot
        self._rotation_task: Optional[asyncio.Task] = None
        self._promo_task: Optional[asyncio.Task] = None
        self._current_index = 0
        self._is_promo_active = False
        self._running = False

    def _get_status_messages(self) -> List[str]:
        """Get list of status messages with all-time stats.

        Returns:
            List of formatted status messages.
        """
        messages = []

        try:
            # Get XP stats from database
            stats = db.get_xp_stats()
            total_users = stats.get("total_users", 0)
            total_xp = stats.get("total_xp", 0)
            total_messages = stats.get("total_messages", 0)
            total_voice = stats.get("total_voice_minutes", 0)

            # Format numbers nicely
            def format_number(n: int) -> str:
                if n >= 1_000_000:
                    return f"{n/1_000_000:.1f}M"
                elif n >= 1_000:
                    return f"{n/1_000:.1f}K"
                return str(n)

            # Format voice time
            voice_hours = total_voice // 60

            # Build status messages with all-time stats only
            if total_users > 0:
                messages.append(f"🏆 {format_number(total_users)} members ranked")

            if total_xp > 0:
                messages.append(f"⭐ {format_number(total_xp)} total XP earned")

            if total_messages > 0:
                messages.append(f"💬 {format_number(total_messages)} messages sent")

            if voice_hours > 0:
                messages.append(f"🎙️ {format_number(voice_hours)}h in voice")

        except Exception as e:
            log.tree("Presence Stats Error", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Fallback if no stats available
        if not messages:
            messages = [
                "🇸🇾 discord.gg/syria",
            ]

        return messages

    async def _rotation_loop(self) -> None:
        """Background task that rotates presence every interval."""
        await self.bot.wait_until_ready()

        log.tree("Presence Rotation Started", [
            ("Interval", f"{PRESENCE_UPDATE_INTERVAL}s"),
        ], emoji="🔄")

        while self._running:
            try:
                # Wait first, then check promo status
                await asyncio.sleep(PRESENCE_UPDATE_INTERVAL)

                # Skip if promo is active (check right before changing)
                if self._is_promo_active:
                    continue

                # Get status messages and rotate
                messages = self._get_status_messages()
                if messages:
                    self._current_index = self._current_index % len(messages)
                    status_text = messages[self._current_index]

                    # Double-check promo isn't active right before changing
                    if self._is_promo_active:
                        continue

                    await self.bot.change_presence(
                        activity=discord.Activity(
                            type=discord.ActivityType.watching,
                            name=status_text,
                        )
                    )

                    self._current_index += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.tree("Presence Rotation Error", [
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
                await asyncio.sleep(PRESENCE_UPDATE_INTERVAL)

    async def _promo_loop(self) -> None:
        """Background task that shows promo at the top of each hour."""
        await self.bot.wait_until_ready()

        log.tree("Promo Loop Started", [
            ("Duration", f"{PROMO_DURATION_MINUTES} min/hour"),
            ("Text", PROMO_TEXT),
        ], emoji="📢")

        while self._running:
            try:
                # Calculate time until next hour
                now = datetime.now(TIMEZONE_EST)
                minutes_until_hour = 60 - now.minute
                seconds_until_hour = (minutes_until_hour * 60) - now.second

                if seconds_until_hour > 0:
                    log.tree("Promo Waiting", [
                        ("Next Promo", f"{minutes_until_hour} min"),
                    ], emoji="⏳")
                    await asyncio.sleep(seconds_until_hour)

                # Show promo
                self._is_promo_active = True

                await self.bot.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.playing,
                        name=PROMO_TEXT,
                    )
                )

                log.tree("Promo Active", [
                    ("Text", PROMO_TEXT),
                    ("Duration", f"{PROMO_DURATION_MINUTES} min"),
                ], emoji="📢")

                # Wait for promo duration
                await asyncio.sleep(PROMO_DURATION_MINUTES * 60)

                # End promo
                self._is_promo_active = False

                log.tree("Promo Ended", [
                    ("Resuming", "Normal rotation"),
                ], emoji="🔄")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._is_promo_active = False
                log.tree("Promo Loop Error", [
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
                await asyncio.sleep(60)

    async def start(self) -> None:
        """Start the presence handler tasks."""
        if self._running:
            return

        self._running = True

        # Start rotation task
        self._rotation_task = asyncio.create_task(self._rotation_loop())

        # Start promo task
        self._promo_task = asyncio.create_task(self._promo_loop())

        log.tree("Presence Handler Started", [
            ("Rotation", f"Every {PRESENCE_UPDATE_INTERVAL}s"),
            ("Promo", f"{PROMO_DURATION_MINUTES} min/hour"),
        ], emoji="✅")

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

        log.tree("Presence Handler Stopped", [
            ("Status", "Tasks cancelled"),
        ], emoji="🛑")
