"""
SyriaBot - FAQ Views
====================

Interactive buttons for FAQ embeds with persistent view support.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import ui
from typing import Optional

from src.core.logger import logger
from src.core.colors import COLOR_SYRIA_GREEN, EMOJI_TICKET
from src.utils.footer import set_footer
from src.services.faq.service import FAQ_DATA, faq_analytics
from src.core.config import config


def _create_faq_embed(topic: str, lang: str) -> discord.Embed:
    """Create FAQ embed in specified language."""
    faq = FAQ_DATA.get(topic)
    if not faq:
        return discord.Embed(
            title="FAQ Not Found",
            description="This FAQ topic doesn't exist.",
            color=COLOR_SYRIA_GREEN,
        )

    embed = discord.Embed(
        title=faq["title"].get(lang, faq["title"]["en"]),
        description=faq["description"].get(lang, faq["description"]["en"]),
        color=COLOR_SYRIA_GREEN,
    )
    set_footer(embed)
    return embed


class PersistentFAQView(ui.View):
    """
    Persistent FAQ view that survives bot restarts.

    Uses custom_id format: faq:{topic}:{lang}
    """

    def __init__(self, topic: str, current_lang: str = "en") -> None:
        super().__init__(timeout=None)  # No timeout for persistent views
        self.topic = topic
        self.current_lang = current_lang
        self._update_buttons()

    def _update_buttons(self) -> None:
        """Update button custom_ids and labels based on current state."""
        self.clear_items()

        # Arabic toggle button
        arabic_btn = ui.Button(
            label="English" if self.current_lang == "ar" else "العربية",
            emoji="🇸🇦",
            style=discord.ButtonStyle.secondary,
            custom_id=f"faq:lang:{self.topic}:{self.current_lang}",
        )
        arabic_btn.callback = self._toggle_language
        self.add_item(arabic_btn)

        # Ticket button
        ticket_btn = ui.Button(
            label="Open Ticket",
            emoji=discord.PartialEmoji.from_str(EMOJI_TICKET),
            style=discord.ButtonStyle.secondary,
            custom_id=f"faq:ticket:{self.topic}",
        )
        ticket_btn.callback = self._open_ticket
        self.add_item(ticket_btn)

    async def _toggle_language(self, interaction: discord.Interaction) -> None:
        """Toggle between English and Arabic."""
        # Parse current state from custom_id
        parts = interaction.data.get("custom_id", "").split(":")
        if len(parts) >= 4:
            self.topic = parts[2]
            current = parts[3]
        else:
            current = "en"

        # Toggle
        new_lang = "en" if current == "ar" else "ar"
        self.current_lang = new_lang

        if new_lang == "ar":
            faq_analytics.record_language_switch(self.topic)

        # Update buttons and embed
        self._update_buttons()
        embed = _create_faq_embed(self.topic, new_lang)
        await interaction.response.edit_message(embed=embed, view=self)

        logger.tree("FAQ Language Switched", [
            ("User", f"{interaction.user.name}"),
            ("Topic", self.topic),
            ("Language", new_lang.upper()),
        ], emoji="🌐")

    async def _open_ticket(self, interaction: discord.Interaction) -> None:
        """Direct user to open a ticket."""
        # Parse topic from custom_id
        parts = interaction.data.get("custom_id", "").split(":")
        if len(parts) >= 3:
            topic = parts[2]
        else:
            topic = "unknown"

        faq_analytics.record_ticket_click()

        await interaction.response.send_message(
            f"Need more help? Open a ticket in <#{config.INBOX_CHANNEL_ID}>",
            ephemeral=True
        )

        logger.tree("FAQ Ticket Click", [
            ("User", f"{interaction.user.name}"),
            ("Topic", topic),
        ], emoji="🎫")


class FAQPersistentHandler(ui.View):
    """
    Handler for persistent FAQ interactions.

    Register this once on bot startup to handle all FAQ button clicks
    for messages sent before bot restart.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(custom_id="faq:lang", style=discord.ButtonStyle.secondary)
    async def lang_handler(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Handle language toggle from persistent messages."""
        # Parse state from actual custom_id
        parts = interaction.data.get("custom_id", "").split(":")
        if len(parts) < 4:
            await interaction.response.defer()
            return

        topic = parts[2]
        current_lang = parts[3]
        new_lang = "en" if current_lang == "ar" else "ar"

        if new_lang == "ar":
            faq_analytics.record_language_switch(topic)

        # Create new view with updated state
        view = PersistentFAQView(topic=topic, current_lang=new_lang)
        embed = _create_faq_embed(topic, new_lang)

        await interaction.response.edit_message(embed=embed, view=view)

        logger.tree("FAQ Language Switched (Persistent)", [
            ("User", f"{interaction.user.name}"),
            ("Topic", topic),
            ("Language", new_lang.upper()),
        ], emoji="🌐")

    @ui.button(custom_id="faq:ticket", style=discord.ButtonStyle.secondary)
    async def ticket_handler(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Handle ticket button from persistent messages."""
        parts = interaction.data.get("custom_id", "").split(":")
        topic = parts[2] if len(parts) >= 3 else "unknown"

        faq_analytics.record_ticket_click()

        await interaction.response.send_message(
            f"Need more help? Open a ticket in <#{config.INBOX_CHANNEL_ID}>",
            ephemeral=True
        )

        logger.tree("FAQ Ticket Click (Persistent)", [
            ("User", f"{interaction.user.name}"),
            ("Topic", topic),
        ], emoji="🎫")


# Alias for backwards compatibility
FAQView = PersistentFAQView


def setup_persistent_views(bot: discord.Client) -> None:
    """Register persistent FAQ views with the bot. Call this in setup_hook."""
    bot.add_view(FAQPersistentHandler())
    logger.tree("FAQ Persistent Views", [
        ("Status", "Registered"),
    ], emoji="✅")
