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

from src.core.logger import logger
from src.core.colors import COLOR_SYRIA_GREEN, COLOR_ERROR
from src.utils.footer import set_footer
from src.services.birthday import get_birthday_service, MONTH_NAMES


class BirthdayCog(commands.Cog):
    """
    Birthday commands for registering your birthday.

    DESIGN:
        Users register with /birthday set (month, day, year). On their birthday,
        they receive the birthday role automatically (assigned by background task).
        Admins can remove birthdays, and /birthday list shows upcoming ones.
        Age validation ensures reasonable birth years.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the birthday cog.

        Args:
            bot: Main bot instance for guild access.
        """
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
            logger.tree("Birthday Set Rejected", [
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

            logger.tree("Birthday Set", [
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

            logger.tree("Birthday Set Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", message),
            ], emoji="⚠️")

    @birthday_group.command(
        name="remove",
        description="Remove a user's birthday (Admin only)"
    )
    @app_commands.describe(user="The user whose birthday to remove")
    @app_commands.default_permissions(moderate_members=True)
    async def birthday_remove(
        self,
        interaction: discord.Interaction,
        user: discord.Member
    ) -> None:
        """Remove a user's birthday (Admin only)."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
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

        success, message = await service.remove_birthday(user)

        if success:
            embed = discord.Embed(
                description=f"Birthday removed for {user.mention}.",
                color=COLOR_SYRIA_GREEN
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            set_footer(embed)

            await interaction.response.send_message(embed=embed, ephemeral=True)

            logger.tree("Birthday Removed (Admin)", [
                ("Admin", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("Target", f"{user.name} ({user.display_name})"),
                ("Target ID", str(user.id)),
            ], emoji="🗑️")
        else:
            embed = discord.Embed(
                description=f"**{message}**",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)

            logger.tree("Birthday Remove Failed", [
                ("Admin", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("Target", f"{user.name} ({user.display_name})"),
                ("Reason", message),
            ], emoji="ℹ️")


    @birthday_group.command(
        name="list",
        description="View upcoming birthdays"
    )
    async def birthday_list(self, interaction: discord.Interaction) -> None:
        """List upcoming birthdays."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
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

        # Get upcoming birthdays
        from src.services.database import db
        import asyncio

        now = datetime.now()
        upcoming = await asyncio.to_thread(
            db.get_upcoming_birthdays,
            interaction.guild.id,
            now.month,
            now.day,
            10  # Limit to 10
        )

        if not upcoming:
            embed = discord.Embed(
                description="No birthdays registered yet.\n\n*Use `/birthday set` to register yours!*",
                color=COLOR_SYRIA_GREEN
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed)
            return

        # Build the list with accurate days calculation
        lines = []
        current_year = now.year

        for i, bday in enumerate(upcoming, 1):
            user = interaction.guild.get_member(bday["user_id"])
            if not user:
                continue

            month = bday["birth_month"]
            day = bday["birth_day"]
            birth_year = bday.get("birth_year")
            month_name = MONTH_NAMES[month]

            # Calculate accurate days until birthday
            try:
                # Try this year first
                next_bday = datetime(current_year, month, day)
                if next_bday.date() < now.date():
                    # Birthday passed this year, use next year
                    next_bday = datetime(current_year + 1, month, day)
                days_until = (next_bday.date() - now.date()).days
            except ValueError:
                # Invalid date (e.g., Feb 29 on non-leap year)
                days_until = bday.get("days_until", 0)

            # Format days text
            if days_until == 0:
                days_text = "**Today!** 🎉"
            elif days_until == 1:
                days_text = "Tomorrow"
            elif days_until <= 7:
                days_text = f"in {days_until} days"
            else:
                days_text = f"{month_name} {day}"

            # Calculate age they'll be turning
            if birth_year:
                turning_year = current_year if days_until > 0 or (days_until == 0) else current_year
                if days_until == 0:
                    age_text = f"(turning {current_year - birth_year})"
                else:
                    next_age = (current_year if datetime(current_year, month, day).date() >= now.date() else current_year + 1) - birth_year
                    age_text = f"(turning {next_age})"
            else:
                age_text = ""

            lines.append(f"**{i}.** {user.mention} — {days_text} {age_text}")

        if not lines:
            embed = discord.Embed(
                description="No birthdays registered yet.\n\n*Use `/birthday set` to register yours!*",
                color=COLOR_SYRIA_GREEN
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed)
            return

        embed = discord.Embed(
            title="Upcoming Birthdays",
            description="\n".join(lines),
            color=COLOR_SYRIA_GREEN
        )
        embed.add_field(
            name="\u200b",
            value="*Use `/birthday set` to register yours!*",
            inline=False
        )
        set_footer(embed)

        await interaction.response.send_message(embed=embed)

        logger.tree("Birthday List Viewed", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Count", str(len(lines))),
        ], emoji="🎂")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(BirthdayCog(bot))
    logger.tree("Command Loaded", [
        ("Name", "birthday (set, remove, list)"),
    ], emoji="✅")
