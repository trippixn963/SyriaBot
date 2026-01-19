"""
SyriaBot - FAQ Command
======================

Moderator command to quickly respond with FAQ templates.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from src.core.config import config
from src.core.logger import log
from src.core.colors import COLOR_SYRIA_GREEN
from src.utils.footer import set_footer
from src.services.faq import FAQ_DATA, faq_analytics, FAQView


# =============================================================================
# FAQ Cog
# =============================================================================

class FAQCog(commands.Cog):
    """Moderator FAQ response system."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def faq_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for FAQ topics."""
        choices = []
        for key, faq in FAQ_DATA.items():
            title = faq["title"]["en"]
            if current.lower() in key.lower() or current.lower() in title.lower():
                choices.append(app_commands.Choice(name=title, value=key))

        return choices[:25]  # Discord limit

    @app_commands.command(
        name="faq",
        description="Send a FAQ response (Moderator only)"
    )
    @app_commands.describe(
        topic="The FAQ topic to send",
        user="Optional: mention a user in the response"
    )
    @app_commands.autocomplete(topic=faq_autocomplete)
    @app_commands.default_permissions(moderate_members=True)
    async def faq(
        self,
        interaction: discord.Interaction,
        topic: str,
        user: Optional[discord.Member] = None,
    ) -> None:
        """Send a FAQ response."""
        if topic not in FAQ_DATA:
            await interaction.response.send_message(
                f"❌ Unknown FAQ topic: `{topic}`\n"
                f"Available: {', '.join(FAQ_DATA.keys())}",
                ephemeral=True
            )
            return

        faq = FAQ_DATA[topic]

        # Create embed (default English)
        embed = discord.Embed(
            title=faq["title"]["en"],
            description=faq["description"]["en"],
            color=COLOR_SYRIA_GREEN,
        )
        set_footer(embed)

        # Create view with buttons
        view = FAQView(topic=topic, current_lang="en")

        # Build response content
        content = None
        if user:
            content = f"{user.mention}"

        await interaction.response.send_message(
            content=content,
            embed=embed,
            view=view,
        )

        # Store message reference for timeout handling
        msg = await interaction.original_response()
        view.message = msg

        # Record analytics
        faq_analytics.record_trigger(topic)

        log.tree("FAQ Sent", [
            ("Moderator", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("Topic", topic),
            ("Target User", user.name if user else "None"),
        ], emoji="📋")



# =============================================================================
# Setup
# =============================================================================

async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(FAQCog(bot))
    log.tree("Command Loaded", [
        ("Name", "faq"),
        ("Topics", str(len(FAQ_DATA))),
    ], emoji="✅")
