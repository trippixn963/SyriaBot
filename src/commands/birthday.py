"""
SyriaBot - Birthday Command
===========================

Set or remove your birthday. Get the birthday role on your special day!

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from src.core.logger import log
from src.core.colors import COLOR_SYRIA_GREEN, COLOR_ERROR
from src.utils.footer import set_footer
from src.services.birthday_service import get_birthday_service, MONTH_NAMES


class BirthdayCog(commands.Cog):
    """Birthday commands for registering your birthday."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    birthday_group = app_commands.Group(
        name="birthday",
        description="Set or remove your birthday"
    )

    @birthday_group.command(
        name="set",
        description="Set your birthday to receive the birthday role"
    )
    @app_commands.describe(
        month="Your birth month",
        day="Your birth day (1-31)",
        year="Your birth year"
    )
    @app_commands.choices(month=[
        app_commands.Choice(name="January", value=1),
        app_commands.Choice(name="February", value=2),
        app_commands.Choice(name="March", value=3),
        app_commands.Choice(name="April", value=4),
        app_commands.Choice(name="May", value=5),
        app_commands.Choice(name="June", value=6),
        app_commands.Choice(name="July", value=7),
        app_commands.Choice(name="August", value=8),
        app_commands.Choice(name="September", value=9),
        app_commands.Choice(name="October", value=10),
        app_commands.Choice(name="November", value=11),
        app_commands.Choice(name="December", value=12),
    ])
    async def birthday_set(
        self,
        interaction: discord.Interaction,
        month: int,
        day: app_commands.Range[int, 1, 31],
        year: int
    ) -> None:
        """Set your birthday."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Unable to set birthday.",
                ephemeral=True
            )
            return

        service = get_birthday_service()
        if not service or not service._enabled:
            await interaction.response.send_message(
                "Birthday feature is not available.",
                ephemeral=True
            )
            log.tree("Birthday Set Rejected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service not enabled"),
            ], emoji="⚠️")
            return

        success, message = await service.set_birthday(interaction.user, month, day, year)

        if success:
            # Calculate age for display
            current_year = datetime.now().year
            age = current_year - year

            embed = discord.Embed(
                title="Birthday Registered!",
                description=(
                    f"{interaction.user.mention} has set their birthday to "
                    f"**{MONTH_NAMES[month]} {day}, {year}**!"
                ),
                color=COLOR_SYRIA_GREEN
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.add_field(
                name="\u200b",
                value="*Use `/birthday set` to register yours!*",
                inline=False
            )
            set_footer(embed)

            await interaction.response.send_message(embed=embed)

            log.tree("Birthday Set", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Birthday", f"{MONTH_NAMES[month]} {day}, {year}"),
            ], emoji="🎂")
        else:
            embed = discord.Embed(
                description=f"**{message}**",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)

            log.tree("Birthday Set Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", message),
            ], emoji="⚠️")

    @birthday_group.command(
        name="remove",
        description="Remove your birthday from the system"
    )
    async def birthday_remove(self, interaction: discord.Interaction) -> None:
        """Remove your birthday."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Unable to remove birthday.",
                ephemeral=True
            )
            return

        service = get_birthday_service()
        if not service:
            await interaction.response.send_message(
                "Birthday feature is not available.",
                ephemeral=True
            )
            return

        success, message = await service.remove_birthday(interaction.user)

        if success:
            embed = discord.Embed(
                description="Your birthday has been removed.",
                color=COLOR_SYRIA_GREEN
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.add_field(
                name="\u200b",
                value="*Use `/birthday set` to register it again!*",
                inline=False
            )
            set_footer(embed)

            await interaction.response.send_message(embed=embed, ephemeral=True)

            log.tree("Birthday Removed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ], emoji="🗑️")
        else:
            embed = discord.Embed(
                description=f"**{message}**",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)

            log.tree("Birthday Remove Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", message),
            ], emoji="ℹ️")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(BirthdayCog(bot))
    log.tree("Command Loaded", [
        ("Name", "birthday (set, remove)"),
    ], emoji="✅")
