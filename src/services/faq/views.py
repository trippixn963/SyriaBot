"""
SyriaBot - FAQ Views
====================

Interactive buttons for FAQ embeds.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import ui
from typing import Optional

from src.core.logger import log
from src.core.colors import COLOR_SYRIA_GREEN, EMOJI_COMMENT
from src.utils.footer import set_footer
from src.services.faq.service import FAQ_DATA, faq_analytics


# Inbox channel for tickets
INBOX_CHANNEL_ID = 1406750411779604561


class FAQView(ui.View):
    """Interactive view for FAQ embeds with language toggle and feedback."""

    def __init__(
        self,
        topic: str,
        current_lang: str = "en",
        timeout: float = 300,
    ):
        super().__init__(timeout=timeout)
        self.topic = topic
        self.current_lang = current_lang
        self.message: Optional[discord.Message] = None
        self._voted_users: set[int] = set()  # Track who voted to prevent double voting

    def _create_embed(self, lang: str) -> discord.Embed:
        """Create FAQ embed in specified language."""
        faq = FAQ_DATA.get(self.topic)
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

    @ui.button(
        label="العربية",
        emoji="🇸🇦",
        style=discord.ButtonStyle.secondary,
        custom_id="faq_arabic",
    )
    async def arabic_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Switch to Arabic."""
        if self.current_lang == "ar":
            # Already in Arabic, switch to English
            self.current_lang = "en"
            button.label = "العربية"
        else:
            # Switch to Arabic
            self.current_lang = "ar"
            button.label = "English"
            faq_analytics.record_language_switch(self.topic)

        embed = self._create_embed(self.current_lang)
        await interaction.response.edit_message(embed=embed, view=self)

        log.tree("FAQ Language Switched", [
            ("User", f"{interaction.user.name}"),
            ("Topic", self.topic),
            ("Language", self.current_lang.upper()),
        ], emoji="🌐")

    @ui.button(
        label="Open Ticket",
        emoji=discord.PartialEmoji.from_str(EMOJI_COMMENT),
        style=discord.ButtonStyle.secondary,
        custom_id="faq_ticket",
    )
    async def ticket_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Direct user to open a ticket."""
        faq_analytics.record_ticket_click()

        await interaction.response.send_message(
            f"Need more help? Open a ticket in <#{INBOX_CHANNEL_ID}>",
            ephemeral=True
        )

        log.tree("FAQ Ticket Click", [
            ("User", f"{interaction.user.name}"),
            ("Topic", self.topic),
        ], emoji="🎫")

    async def on_timeout(self) -> None:
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
            except Exception as e:
                log.tree("FAQ View Timeout Error", [
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
