"""
SyriaBot - AFK Command
======================

Dyno-style AFK system. Set yourself as AFK with an optional reason.
When mentioned, bot notifies others you're AFK.
When you send a message, AFK is automatically removed.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time

import discord
from discord import app_commands
from discord.ext import commands

from src.core.logger import log
from src.utils.footer import set_footer
from src.services.database import db


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
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
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
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service not initialized"),
            ], emoji="⚠️")
            return

        # Check if user is already AFK
        existing_afk = db.get_afk(interaction.user.id, interaction.guild.id)
        if existing_afk:
            await interaction.response.send_message(
                f"You're already AFK since <t:{existing_afk['timestamp']}:R>",
                ephemeral=True
            )
            log.tree("AFK Command Rejected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Already AFK"),
            ], emoji="ℹ️")
            return

        # Use AFK service to set status and handle nickname
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Unable to set AFK status.",
                ephemeral=True
            )
            log.tree("AFK Command Rejected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "User is not a Member"),
            ], emoji="⚠️")
            return

        _, converted_reason = await self.bot.afk_service.set_afk(interaction.user, reason or "")

        # Build response - thumbnail design with mention
        now = int(time.time())

        embed = discord.Embed(color=0x1F5E2E)  # Syria green
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        if converted_reason:
            embed.description = f"💤 {interaction.user.mention} is now AFK\n\n{converted_reason}\n"
        else:
            embed.description = f"💤 {interaction.user.mention} is now AFK"

        embed.add_field(name="", value=f"-# Set <t:{now}:R>", inline=False)
        set_footer(embed)

        try:
            await interaction.response.send_message(embed=embed)
            log.tree("AFK Command", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Guild", interaction.guild.name),
                ("Reason", converted_reason[:50] if converted_reason else "None"),
            ], emoji="💤")
        except discord.HTTPException as e:
            log.tree("AFK Response Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(AFKCog(bot))
    log.tree("Command Loaded", [
        ("Name", "afk"),
    ], emoji="✅")
