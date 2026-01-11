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
    @app_commands.guilds(discord.Object(id=config.GUILD_ID))
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

    @app_commands.command(
        name="faqstats",
        description="View FAQ analytics (Moderator only)"
    )
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guilds(discord.Object(id=config.GUILD_ID))
    async def faqstats(self, interaction: discord.Interaction) -> None:
        """View FAQ usage statistics."""
        stats = faq_analytics.get_stats()
        top_faqs = faq_analytics.get_top_faqs(5)

        embed = discord.Embed(
            title="📊 FAQ Analytics",
            color=COLOR_SYRIA_GREEN,
        )

        # Overview
        embed.add_field(
            name="Overview",
            value=f"**Total Triggers:** {stats['total_triggers']}\n"
                  f"**Helpful Votes:** {stats['total_helpful']}\n"
                  f"**Unhelpful Votes:** {stats['total_unhelpful']}\n"
                  f"**Ticket Clicks:** {stats['ticket_clicks']}",
            inline=False,
        )

        # Top FAQs
        if top_faqs:
            top_list = "\n".join([f"• **{topic}**: {count}" for topic, count in top_faqs])
            embed.add_field(
                name="Top FAQs",
                value=top_list,
                inline=False,
            )

        # Language switches
        total_switches = sum(stats["language_switches"].values())
        if total_switches > 0:
            embed.add_field(
                name="Arabic Switches",
                value=f"**Total:** {total_switches}",
                inline=False,
            )

        set_footer(embed)
        await interaction.response.send_message(embed=embed, ephemeral=True)


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
