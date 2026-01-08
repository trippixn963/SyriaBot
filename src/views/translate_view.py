"""
SyriaBot - Translate View
=========================

Interactive buttons for translation.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import ui
from typing import Optional

from src.core.logger import log
from src.core.config import config
from src.core.colors import COLOR_GOLD, COLOR_SUCCESS
from src.services.translate_service import translate_service, LANGUAGES
from src.utils.footer import set_footer


# Priority languages for quick buttons
PRIORITY_LANGUAGES = [
    ("en", "English", "🇬🇧"),
    ("ar", "Arabic", "🇸🇦"),
    ("fr", "French", "🇫🇷"),
    ("de", "German", "🇩🇪"),
    ("es", "Spanish", "🇪🇸"),
    ("ru", "Russian", "🇷🇺"),
    ("tr", "Turkish", "🇹🇷"),
    ("zh-CN", "Chinese", "🇨🇳"),
]

# Custom emoji IDs
AI_EMOJI = "<:AI:1456695002271977515>"


class LanguageSelect(ui.Select):
    """Dropdown to select a language for translation."""

    def __init__(self, original_text: str, current_lang: str, shown_buttons: set):
        self.original_text = original_text

        options = []
        extra_langs = ["it", "pt", "ja", "ko", "nl", "pl", "hi", "iw", "fa", "ur", "sv", "el", "cs", "th", "vi", "id", "uk", "ro", "hu", "da", "no", "fi", "ms"]

        for code, label, emoji in PRIORITY_LANGUAGES:
            if code == current_lang or code in shown_buttons:
                continue
            options.append(discord.SelectOption(
                label=label,
                value=code,
                emoji=emoji,
            ))

        for code in extra_langs:
            if code == current_lang:
                continue
            if code in LANGUAGES:
                name, flag = LANGUAGES[code]
                options.append(discord.SelectOption(
                    label=name,
                    value=code,
                    emoji=flag,
                ))
            if len(options) >= 25:
                break

        super().__init__(
            placeholder="More languages...",
            options=options if options else [discord.SelectOption(label="No more languages", value="none")],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]

        if selected == "none":
            log.tree("Language Select", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Selected", "none"),
                ("Action", "Ignored - no languages available"),
            ], emoji="🌐")
            await interaction.response.defer()
            return

        # Get language name for logging
        lang_name = LANGUAGES.get(selected, (selected, ""))[0]

        log.tree("Language Select", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Selected", f"{lang_name} ({selected})"),
        ], emoji="🌐")

        await self.view.translate_to(interaction, selected)


class TranslateView(ui.View):
    """Interactive view for translation with language buttons."""

    def __init__(
        self,
        original_text: str,
        requester_id: int,
        current_lang: str = "en",
        source_lang: str = "auto",
        timeout: float = 300,
    ):
        super().__init__(timeout=timeout)
        self.original_text = original_text
        self.requester_id = requester_id
        self.current_lang = current_lang
        self.source_lang = source_lang
        self.message: Optional[discord.Message] = None

        self._rebuild_buttons()

    def _rebuild_buttons(self):
        """Rebuild buttons based on current and source language."""
        self.clear_items()

        shown_buttons = set()
        button_count = 0

        # Skip both source (original already shown) and current (already translated to)
        skip_langs = {self.current_lang}
        if self.source_lang and self.source_lang != "auto":
            skip_langs.add(self.source_lang)

        # Fill with priority languages (excluding source and current)
        for code, label, emoji in PRIORITY_LANGUAGES:
            if code in skip_langs:
                continue

            button = ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.secondary,
                custom_id=f"translate_{code}",
                row=1,
            )
            button.callback = self._make_button_callback(code, label)
            self.add_item(button)
            shown_buttons.add(code)

            button_count += 1
            if button_count >= 4:
                break

        self.add_item(LanguageSelect(self.original_text, self.current_lang, shown_buttons | skip_langs))

        # AI button (boosters only) - same row as language buttons
        ai_button = ui.Button(
            label="AI",
            emoji=discord.PartialEmoji.from_str(AI_EMOJI),
            style=discord.ButtonStyle.secondary,
            custom_id="translate_ai",
            row=1,
        )
        ai_button.callback = self._ai_button_callback
        self.add_item(ai_button)

    def _make_button_callback(self, target_lang: str, lang_name: str):
        """Create a callback for a language button."""
        async def callback(interaction: discord.Interaction):
            log.tree("Language Button Pressed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Language", f"{lang_name} ({target_lang})"),
                ("Current Lang", self.current_lang),
            ], emoji="🌐")
            await self.translate_to(interaction, target_lang)
        return callback

    async def _ai_button_callback(self, interaction: discord.Interaction):
        """Handle AI translate button - boosters only."""
        log.tree("AI Button Pressed", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Current Lang", self.current_lang),
        ], emoji="🤖")

        # Check if user is a booster
        is_booster = False
        if isinstance(interaction.user, discord.Member) and config.BOOSTER_ROLE_ID:
            booster_role = interaction.user.get_role(config.BOOSTER_ROLE_ID)
            if booster_role:
                is_booster = True

        if not is_booster:
            # Create nice embed for non-boosters (green/gold theme)
            embed = discord.Embed(
                title="✨ Booster Exclusive Feature",
                description=(
                    "**AI Translation** uses GPT-4o to provide higher quality, "
                    "context-aware translations.\n\n"
                    "This premium feature is exclusively available to **Server Boosters** "
                    "as a thank you for supporting the community!"
                ),
                color=COLOR_SUCCESS  # Green
            )
            embed.add_field(
                name="🏆 How to Unlock",
                value="Boost the server to instantly unlock AI translations and other booster perks!",
                inline=False
            )
            set_footer(embed)

            await interaction.response.send_message(embed=embed)  # Public to encourage boosting

            log.tree("AI Button Rejected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Not a booster"),
                ("Action", "Sent booster promo embed"),
            ], emoji="🚫")
            return

        log.tree("AI Translation Started", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Target Lang", self.current_lang),
            ("Text Length", str(len(self.original_text))),
        ], emoji="🤖")

        await interaction.response.defer()

        result = await translate_service.translate_ai(
            self.original_text,
            target_lang=self.current_lang,
        )

        if not result.success:
            error_msg = "AI translation failed. Please try again."
            if result.error and len(result.error) < 100:
                error_msg = result.error
            await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)

            log.tree("AI Translation Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Target", self.current_lang),
                ("Error", result.error[:100] if result.error else "Unknown"),
            ], emoji="❌")
            return

        embed, file = create_translate_embed(result, is_ai=True)
        if file:
            await interaction.edit_original_response(embed=embed, attachments=[file], view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)

        log.tree("AI Translation Complete", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("From", f"{result.source_name} ({result.source_lang})"),
            ("To", f"{result.target_name} ({result.target_lang})"),
            ("Result Length", str(len(result.translated_text))),
        ], emoji="✅")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the requester to use buttons."""
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who requested this translation can use these buttons.",
                ephemeral=True
            )
            log.tree("Translate Interaction Rejected", [
                ("Attempted By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("Attempted By ID", str(interaction.user.id)),
                ("Owner ID", str(self.requester_id)),
                ("Reason", "Not command owner"),
            ], emoji="🚫")
            return False
        return True

    async def on_timeout(self) -> None:
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True

        if hasattr(self, 'message') and self.message:
            try:
                await self.message.edit(view=self)
                log.tree("Translate View Timeout", [
                    ("Requester ID", str(self.requester_id)),
                    ("Current Lang", self.current_lang),
                    ("Action", "Disabled all buttons"),
                ], emoji="⏳")
            except discord.NotFound:
                log.tree("Translate View Timeout", [
                    ("Requester ID", str(self.requester_id)),
                    ("Reason", "Message deleted"),
                ], emoji="⏳")
            except Exception as e:
                log.tree("Translate View Timeout Error", [
                    ("Requester ID", str(self.requester_id)),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

    async def translate_to(self, interaction: discord.Interaction, target_lang: str):
        """Translate to a new language and update the embed."""
        if target_lang == self.current_lang:
            log.tree("Translation Skipped", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", f"Already in {target_lang}"),
            ], emoji="⚠️")
            await interaction.response.defer()
            return

        log.tree("Re-translation Started", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("From Lang", self.current_lang),
            ("To Lang", target_lang),
            ("Text Length", str(len(self.original_text))),
        ], emoji="🌐")

        await interaction.response.defer()

        result = await translate_service.translate(
            self.original_text,
            target_lang=target_lang,
            source_lang="auto"
        )

        if not result.success:
            error_msg = "Translation failed. Please try again."
            if result.error and len(result.error) < 100:
                error_msg = result.error
            await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)

            log.tree("Re-translation Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Target", target_lang),
                ("Error", result.error[:100] if result.error else "Unknown"),
            ], emoji="❌")
            return

        if result.source_lang == result.target_lang:
            target_name = LANGUAGES.get(result.target_lang, (result.target_lang, "🌐"))[0]
            await interaction.followup.send(
                f"This text is already in {target_name}.",
                ephemeral=True
            )

            log.tree("Re-translation Skipped", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", f"Text already in {target_name}"),
            ], emoji="⚠️")
            return

        self.current_lang = target_lang
        self.source_lang = result.source_lang
        self._rebuild_buttons()

        embed, file = create_translate_embed(result)
        if file:
            await interaction.edit_original_response(embed=embed, attachments=[file], view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)

        log.tree("Re-translation Complete", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("From", f"{result.source_name} ({result.source_lang})"),
            ("To", f"{result.target_name} ({result.target_lang})"),
            ("Result Length", str(len(result.translated_text))),
        ], emoji="✅")


def create_translate_embed(result, is_ai: bool = False) -> tuple[discord.Embed, discord.File | None]:
    """
    Create a translation embed with code blocks.

    Returns (embed, file) - file is provided when text is too long for embed.
    """
    import io

    if is_ai:
        title = f"{AI_EMOJI} {result.source_flag} → {result.target_flag} AI Translation"
        color = COLOR_SUCCESS  # Green for AI
    else:
        title = f"{result.source_flag} → {result.target_flag} Translation"
        color = COLOR_GOLD  # Gold for regular

    embed = discord.Embed(
        title=title,
        color=color
    )

    # Check if we need a file for long text
    is_long = len(result.original_text) > 800 or len(result.translated_text) > 800
    file = None

    original_display = result.original_text
    if len(original_display) > 900:
        original_display = original_display[:897] + "..."
    embed.add_field(
        name=f"Original ({result.source_name})",
        value=f"```\n{original_display}\n```",
        inline=False
    )

    translated_display = result.translated_text
    if len(translated_display) > 900:
        translated_display = translated_display[:897] + "..."
    embed.add_field(
        name=f"Translation ({result.target_name})",
        value=f"```\n{translated_display}\n```",
        inline=False
    )

    # Create file with full translation if text was truncated
    if is_long:
        file_content = (
            f"═══ ORIGINAL ({result.source_name}) ═══\n\n"
            f"{result.original_text}\n\n"
            f"═══ TRANSLATION ({result.target_name}) ═══\n\n"
            f"{result.translated_text}"
        )
        file = discord.File(
            fp=io.BytesIO(file_content.encode('utf-8')),
            filename="translation.txt"
        )
        embed.set_footer(text="Full translation attached as file • trippixn.com/Syria")
    else:
        set_footer(embed)

    return embed, file
