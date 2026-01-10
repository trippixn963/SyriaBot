"""
SyriaBot - Giveaway Reaction Handler
====================================

Handles reactions for giveaway entries.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord.ext import commands

from src.core.logger import log
from src.core.colors import EMOJI_GIVEAWAY
from src.services.database import db


class GiveawayHandler(commands.Cog):
    """Handler for giveaway reactions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle reaction add for giveaway entry."""
        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:
            return

        # Check if it's the giveaway emoji
        if str(payload.emoji) != EMOJI_GIVEAWAY:
            return

        # Check if this message is a giveaway
        giveaway = db.get_giveaway_by_message(payload.message_id)
        if not giveaway:
            return

        # Get the member
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member:
            return

        # Enter giveaway
        if hasattr(self.bot, "giveaway_service") and self.bot.giveaway_service:
            success, message = await self.bot.giveaway_service.enter_giveaway(
                giveaway["id"], member
            )

            # If entry failed, remove the reaction
            if not success:
                try:
                    channel = self.bot.get_channel(payload.channel_id)
                    if channel:
                        msg = await channel.fetch_message(payload.message_id)
                        await msg.remove_reaction(payload.emoji, member)
                except Exception as e:
                    log.tree("Giveaway Reaction Remove Failed", [
                        ("User", f"{member.name} ({member.id})"),
                        ("Reason", str(e)[:50]),
                    ], emoji="⚠️")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle reaction remove for giveaway leave."""
        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:
            return

        # Check if it's the giveaway emoji
        if str(payload.emoji) != EMOJI_GIVEAWAY:
            return

        # Check if this message is a giveaway
        giveaway = db.get_giveaway_by_message(payload.message_id)
        if not giveaway:
            return

        # Get the member
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member:
            return

        # Leave giveaway
        if hasattr(self.bot, "giveaway_service") and self.bot.giveaway_service:
            await self.bot.giveaway_service.leave_giveaway(giveaway["id"], member)


async def setup(bot: commands.Bot) -> None:
    """Set up the giveaway handler cog."""
    await bot.add_cog(GiveawayHandler(bot))
