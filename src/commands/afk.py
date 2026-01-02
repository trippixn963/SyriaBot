"""
SyriaBot - AFK Command
======================

Dyno-style AFK system. Set yourself as AFK with an optional reason.
When mentioned, bot notifies others you're AFK.
When you send a message, AFK is automatically removed.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import app_commands
from discord.ext import commands

from src.core.logger import log
from src.core.colors import COLOR_SUCCESS
from src.utils.footer import set_footer


class AFKCog(commands.Cog):
    """AFK command for setting away status."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="afk",
        description="Set yourself as AFK with an optional reason"
    )
    @app_commands.describe(reason="Why you're going AFK (optional)")
    async def afk(self, interaction: discord.Interaction, reason: str = None) -> None:
        """Set yourself as AFK."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True
            )
            log.tree("AFK Command Rejected", [
                ("User", f"{interaction.user.name}"),
                ("User ID", str(interaction.user.id)),
                ("Reason", "Used in DMs"),
            ], emoji="⚠️")
            return

        # Check if AFK service is available
        if not hasattr(self.bot, 'afk_service') or not self.bot.afk_service:
            await interaction.response.send_message(
                "AFK service is not available.",
                ephemeral=True
            )
            log.tree("AFK Command Rejected", [
                ("User", f"{interaction.user.name}"),
                ("User ID", str(interaction.user.id)),
                ("Reason", "Service not initialized"),
            ], emoji="⚠️")
            return

        # Use AFK service to set status and handle nickname
        if isinstance(interaction.user, discord.Member):
            await self.bot.afk_service.set_afk(interaction.user, reason or "")

        # Build response
        import time
        now = int(time.time())

        if reason:
            description = f"You are now AFK: **{reason}**"
        else:
            description = "You are now AFK."

        embed = discord.Embed(
            description=f"💤 {description}",
            color=COLOR_SUCCESS
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Set", value=f"<t:{now}:R>", inline=True)
        embed.add_field(name="Nickname", value=f"`{interaction.user.display_name}`", inline=True)
        set_footer(embed)

        await interaction.response.send_message(embed=embed)

        log.tree("AFK Command", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("User ID", str(interaction.user.id)),
            ("Guild", interaction.guild.name),
            ("Reason", reason[:50] if reason else "None"),
        ], emoji="💤")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(AFKCog(bot))
    log.tree("Command Loaded", [
        ("Name", "afk"),
    ], emoji="✅")
