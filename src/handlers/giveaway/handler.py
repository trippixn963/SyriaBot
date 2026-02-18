"""
SyriaBot - Giveaway Reaction Handler
====================================

Monitors giveaway reactions and enforces level requirements.
Remove this handler after the giveaway ends.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import os
import time
import discord
from discord.ext import commands
from pathlib import Path

from src.core.logger import logger
from src.core.config import config
from src.services.database import db


# =============================================================================
# Configuration
# =============================================================================

GIVEAWAY_CHANNEL_ID = config.GIVEAWAY_CHANNEL_ID
JOIN_EMOJI_ID = 1459322239311937606
REQUIRED_LEVEL = 10
GIVEAWAY_ID_FILE = Path(__file__).parent.parent.parent / "data" / "giveaway_message.txt"


def get_giveaway_message_id() -> int | None:
    """Read giveaway message ID from file."""
    if GIVEAWAY_ID_FILE.exists():
        try:
            return int(GIVEAWAY_ID_FILE.read_text().strip())
        except (ValueError, IOError):
            return None
    return None


class GiveawayReactionHandler(commands.Cog):
    """Handles giveaway reaction validation."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._warned_users: dict[int, float] = {}  # user_id -> timestamp
        self._warn_cooldown = 3600  # 1 hour

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Check if user meets level requirement for giveaway."""
        # Get current giveaway message ID
        giveaway_message_id = get_giveaway_message_id()

        # Skip if no active giveaway
        if giveaway_message_id is None:
            return

        # Skip if not the giveaway message
        if payload.message_id != giveaway_message_id:
            return

        # Skip if not the join emoji
        if not hasattr(payload.emoji, 'id') or payload.emoji.id != JOIN_EMOJI_ID:
            return

        # Skip bots
        if payload.member is None or payload.member.bot:
            return

        # Check user level
        user_id = payload.user_id
        guild_id = payload.guild_id

        xp_data = db.get_user_xp(user_id, guild_id)
        user_level = xp_data.get("level", 0) if xp_data else 0

        if user_level >= REQUIRED_LEVEL:
            # User meets requirement
            logger.tree("Giveaway Entry", [
                ("User", payload.member.name),
                ("ID", str(user_id)),
                ("Level", str(user_level)),
            ], emoji="✅")
            return

        # User doesn't meet requirement - remove reaction
        try:
            channel = self.bot.get_channel(payload.channel_id)
            if channel:
                message = await channel.fetch_message(payload.message_id)
                await message.remove_reaction(payload.emoji, payload.member)

                # Check if user was recently warned (cooldown)
                now = time.time()
                last_warned = self._warned_users.get(user_id, 0)

                if now - last_warned < self._warn_cooldown:
                    # Still on cooldown, just remove reaction silently
                    return

                # Update last warned time
                self._warned_users[user_id] = now

                # Send warning message
                warning = await channel.send(
                    f"{payload.member.mention} You need to be **Level {REQUIRED_LEVEL}+** to enter this giveaway. "
                    f"You are currently Level {user_level}.",
                )

                # Delete after 5 seconds
                await asyncio.sleep(5)
                await warning.delete()

                logger.tree("Giveaway Entry Denied", [
                    ("User", payload.member.name),
                    ("ID", str(user_id)),
                    ("Level", f"{user_level} (need {REQUIRED_LEVEL})"),
                ], emoji="🚫")

        except discord.HTTPException as e:
            logger.error_tree("Giveaway Reaction Remove Failed", e)
        except Exception as e:
            logger.error_tree("Giveaway Handler Error", e)


async def setup(bot: commands.Bot) -> None:
    """Load the cog."""
    await bot.add_cog(GiveawayReactionHandler(bot))
