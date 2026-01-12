"""
SyriaBot - Guide Command
========================

Admin command to post the interactive server guide panel.

Author: John Hamwi
Server: discord.gg/syria
"""

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import config
from src.core.logger import log
from src.core.colors import COLOR_SYRIA_GREEN
from src.utils.footer import set_footer
from src.services.guide.views import GuideView


# =============================================================================
# Guide Cog
# =============================================================================

class GuideCog(commands.Cog):
    """Admin command to post the server guide panel."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="guide",
        description="Post the interactive server guide panel (Admin only)"
    )
    @app_commands.describe(
        channel="Channel to post the guide in (default: current channel)",
        purge="Purge all messages in the channel first (default: True)"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(discord.Object(id=config.GUILD_ID))
    async def guide(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        purge: bool = True
    ) -> None:
        """Post the interactive server guide panel."""
        target = channel or interaction.channel

        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "Guide can only be posted in text channels.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        log.tree("Guide Post Started", [
            ("Admin", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("Channel", target.name),
            ("Purge", str(purge)),
        ], emoji="📋")

        try:
            # Optionally purge all messages in channel first
            if purge:
                deleted = await target.purge(limit=None)
                log.tree("Channel Purged", [
                    ("Channel", target.name),
                    ("Messages Deleted", str(len(deleted))),
                ], emoji="🗑️")

            # Build the main guide panel embed
            guild = interaction.guild
            created_timestamp = int(guild.created_at.timestamp()) if guild else 0

            embed = discord.Embed(
                title="Server Guide",
                description=(
                    "Welcome to the server! Click the buttons below to learn more.\n\n"
                    "**Rules** - `Server rules and guidelines`\n"
                    "**Roles** - `Role system and how to get roles`\n"
                    "**FAQ** - `Frequently asked questions`\n"
                    "**Commands** - `Bot commands and features`"
                ),
                color=COLOR_SYRIA_GREEN,
            )

            # Add server info
            if guild:
                embed.add_field(
                    name="Server Info",
                    value=(
                        f"**Created:** <t:{created_timestamp}:D> (<t:{created_timestamp}:R>)\n"
                        f"**Members:** {guild.member_count:,}\n"
                        f"**Boosters:** {guild.premium_subscription_count or 0}"
                    ),
                    inline=False,
                )

            # Add server banner if available
            if guild and guild.banner:
                embed.set_image(url=guild.banner.url)

            set_footer(embed)

            # Send panel with buttons
            view = GuideView()
            await target.send(embed=embed, view=view)

            await interaction.followup.send(
                f"Guide panel posted to {target.mention}",
                ephemeral=True
            )

            log.tree("Guide Posted", [
                ("Admin", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("Channel", target.name),
            ], emoji="✅")

        except discord.Forbidden:
            await interaction.followup.send(
                f"Missing permissions to send messages in {target.mention}",
                ephemeral=True
            )
            log.tree("Guide Post Failed", [
                ("Channel", target.name),
                ("Reason", "Missing permissions"),
            ], emoji="❌")

        except discord.HTTPException as e:
            await interaction.followup.send(
                f"Failed to post guide: {e}",
                ephemeral=True
            )
            log.error_tree("Guide Post Error", e, [
                ("Channel", target.name),
            ])


# =============================================================================
# Setup
# =============================================================================

async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(GuideCog(bot))
    log.tree("Command Loaded", [
        ("Name", "guide"),
    ], emoji="✅")
