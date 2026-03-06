"""
SyriaBot - Daily Stats Service
==============================

Sends a daily summary embed at midnight EST to the mods channel.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta
from typing import Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks

from src.core.config import config
from src.core.colors import COLOR_GOLD
from src.core.logger import logger
from src.services.database import db

if TYPE_CHECKING:
    from src.bot import SyriaBot

EST = ZoneInfo("America/New_York")


class DailyStatsService:
    """Sends a daily summary embed at midnight EST."""

    def __init__(self, bot: "SyriaBot") -> None:
        self.bot = bot
        self._enabled = False

    async def setup(self) -> None:
        """Start the daily stats task."""
        if not config.DAILY_STATS_CHANNEL_ID:
            logger.tree("Daily Stats Service", [
                ("Status", "Disabled"),
                ("Reason", "SYRIA_DAILY_STATS_CH not configured"),
            ], emoji="ℹ️")
            return

        self._enabled = True
        self.daily_summary.start()

        logger.tree("Daily Stats Service Ready", [
            ("Channel", str(config.DAILY_STATS_CHANNEL_ID)),
            ("Schedule", "Midnight Eastern (DST-aware)"),
        ], emoji="📊")

    def stop(self) -> None:
        """Stop the daily stats task."""
        if self.daily_summary.is_running():
            self.daily_summary.cancel()
        logger.tree("Daily Stats Service Stopped", [], emoji="🛑")

    @tasks.loop(time=dt_time(hour=0, minute=0, tzinfo=EST))  # Midnight Eastern (DST-aware)
    async def daily_summary(self) -> None:
        """Send the daily summary embed."""
        if not self._enabled:
            return

        try:
            await self._send_summary()
        except Exception as e:
            logger.error_tree("Daily Summary Failed", e)

    @daily_summary.before_loop
    async def before_daily_summary(self) -> None:
        """Wait for bot to be ready."""
        await self.bot.wait_until_ready()

    async def _send_summary(self) -> None:
        """Build and send the daily summary embed."""
        channel = self.bot.get_channel(config.DAILY_STATS_CHANNEL_ID)
        if not channel:
            logger.tree("Daily Stats Channel Not Found", [
                ("ID", str(config.DAILY_STATS_CHANNEL_ID)),
            ], emoji="⚠️")
            return

        # Yesterday's date in EST
        now_est = datetime.now(EST)
        yesterday = now_est - timedelta(days=1)
        date_str: str = yesterday.strftime("%Y-%m-%d")
        display_date: str = yesterday.strftime("%b %-d, %Y")

        guild_id: int = config.GUILD_ID

        # Compute EST day boundaries as UTC timestamps for member_events query
        day_start_est = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end_est = day_start_est + timedelta(days=1)
        start_ts: int = int(day_start_est.timestamp())
        end_ts: int = int(day_end_est.timestamp())

        logger.tree("Daily Summary Building", [
            ("Date", date_str),
            ("Guild", str(guild_id)),
        ], emoji="📊")

        # ── Gather data ──────────────────────────────────────────────────

        # Messages from server_daily_stats
        total_messages: int = 0
        try:
            daily_rows = db.get_daily_stats_range(guild_id, date_str, date_str)
            total_messages = daily_rows[0]["total_messages"] if daily_rows else 0
        except Exception as e:
            logger.error_tree("Daily Summary: Messages Query Failed", e)

        # Joins / Leaves from member_events (counted in SQL)
        joins: int = 0
        leaves: int = 0
        try:
            event_counts = db.get_member_event_counts(guild_id, start_ts, end_ts)
            joins = event_counts["joins"]
            leaves = event_counts["leaves"]
        except Exception as e:
            logger.error_tree("Daily Summary: Member Events Query Failed", e)
        net: int = joins - leaves

        # Voice
        total_voice_min: int = 0
        try:
            total_voice_min = db.get_daily_total_voice_minutes(guild_id, date_str)
        except Exception as e:
            logger.error_tree("Daily Summary: Voice Query Failed", e)
        voice_hours: int = total_voice_min // 60
        voice_mins: int = total_voice_min % 60

        # Top chatter & voice user
        top_chatter: dict | None = None
        top_voice: dict | None = None
        try:
            top_chatter = db.get_daily_top_chatter(guild_id, date_str)
        except Exception as e:
            logger.error_tree("Daily Summary: Top Chatter Query Failed", e)
        try:
            top_voice = db.get_daily_top_voice_user(guild_id, date_str)
        except Exception as e:
            logger.error_tree("Daily Summary: Top Voice Query Failed", e)

        # ── Build embed ──────────────────────────────────────────────────

        net_str: str = f"+{net}" if net > 0 else str(net)

        members_block: str = (
            f"```\n"
            f"Joined       {joins:>6,}\n"
            f"Left         {leaves:>6,}\n"
            f"Net          {net_str:>6}\n"
            f"```"
        )

        messages_block: str = (
            f"```\n"
            f"Total      {total_messages:>8,}\n"
            f"```"
        )

        if total_voice_min > 0:
            voice_block: str = (
                f"```\n"
                f"Total      {voice_hours:>4}h {voice_mins:>2}m\n"
                f"```"
            )
        else:
            voice_block = "```\nNo activity\n```"

        # Top of the day
        top_lines: list[str] = []
        if top_chatter:
            top_lines.append(f"\U0001f4ac <@{top_chatter['user_id']}>  {top_chatter['messages']:,} msgs")
        if top_voice:
            vm: int = top_voice["voice_minutes"]
            vh, vmin = vm // 60, vm % 60
            top_lines.append(f"\U0001f399\ufe0f <@{top_voice['user_id']}>  {vh}h {vmin}m")

        top_section: str = "\n".join(top_lines) if top_lines else "No activity"

        embed = discord.Embed(
            title=f"\U0001f4ca Daily Summary \u2014 {display_date}",
            color=COLOR_GOLD,
        )

        embed.add_field(
            name="\U0001f465 Members",
            value=members_block,
            inline=False,
        )
        embed.add_field(
            name="\U0001f4ac Messages Sent",
            value=messages_block,
            inline=False,
        )
        embed.add_field(
            name="\U0001f399\ufe0f Voice Activity",
            value=voice_block,
            inline=False,
        )
        embed.add_field(
            name="\U0001f3c6 Top of the Day",
            value=top_section,
            inline=False,
        )

        # ── Send ─────────────────────────────────────────────────────────

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.tree("Daily Summary Send Failed", [
                ("Channel", str(config.DAILY_STATS_CHANNEL_ID)),
                ("Reason", "Missing permissions"),
            ], emoji="🚫")
            return
        except discord.HTTPException as e:
            logger.error_tree("Daily Summary Send Failed", e, [
                ("Channel", str(config.DAILY_STATS_CHANNEL_ID)),
            ])
            return

        logger.tree("Daily Summary Sent", [
            ("Date", date_str),
            ("Messages", f"{total_messages:,}"),
            ("Joins", str(joins)),
            ("Leaves", str(leaves)),
            ("Voice", f"{voice_hours}h {voice_mins}m"),
            ("Top Chatter", str(top_chatter["user_id"]) if top_chatter else "None"),
            ("Top Voice", str(top_voice["user_id"]) if top_voice else "None"),
        ], emoji="📊")
