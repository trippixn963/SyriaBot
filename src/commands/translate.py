"""
SyriaBot - Translate Command
============================

Slash command to translate text.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import config
from src.core.logger import log
from src.core.colors import COLOR_ERROR, COLOR_WARNING
from src.services.translate import translate_service, find_similar_language
from src.services.translate.views import TranslateView, create_translate_embed
from src.utils.footer import set_footer


class TranslateCog(commands.Cog):
    """Commands for translating text."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="translate",
        description="Translate text to another language"
    )
    @app_commands.describe(
        text="The text to translate",
        to="Target language (e.g., 'ar', 'arabic', 'en', 'english')",
    )
    @app_commands.guilds(discord.Object(id=config.GUILD_ID))
    async def translate(
        self,
        interaction: discord.Interaction,
        text: str,
        to: str = "en",
    ) -> None:
        """Translate text to a target language."""
        await interaction.response.defer()

        log.tree("Translate Command", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Text", text[:50] + "..." if len(text) > 50 else text),
            ("To", to),
        ], emoji="🌐")

        result = await translate_service.translate(text, target_lang=to)

        if not result.success:
            error_msg = "Translation failed. Please try again."
            if result.error:
                if "Unknown language" in result.error or "No support for the provided language" in result.error:
                    similar = find_similar_language(to)
                    if similar:
                        code, name, flag = similar
                        # Don't suggest the same code they already typed
                        if code.lower() == to.lower():
                            error_msg = "Translation service temporarily unavailable. Please try again."
                        else:
                            error_msg = f"Language `{to}` is not supported. Did you mean {flag} **{name}** (`{code}`)?"
                    else:
                        error_msg = f"Language `{to}` is not supported."
                elif len(result.error) < 100:
                    error_msg = result.error

            embed = discord.Embed(
                description=f"❌ {error_msg}",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)

            log.tree("Translation Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Target", to),
                ("Error", result.error[:50] if result.error else "Unknown"),
            ], emoji="❌")
            return

        if result.source_lang == result.target_lang:
            embed = discord.Embed(
                title="🌐 Already in Target Language",
                description=f"This text is already in {result.target_name}.",
                color=COLOR_WARNING
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
            log.tree("Translation Skipped", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", f"Already in {result.target_name}"),
            ], emoji="⚠️")
            return

        embed, file = create_translate_embed(result)

        view = TranslateView(
            original_text=text,
            requester_id=interaction.user.id,
            current_lang=result.target_lang,
            source_lang=result.source_lang,
        )

        if file:
            msg = await interaction.followup.send(embed=embed, file=file, view=view, wait=True)
        else:
            msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        view.message = msg

        log.tree("Translation Sent", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("From", f"{result.source_name} ({result.source_lang})"),
            ("To", f"{result.target_name} ({result.target_lang})"),
        ], emoji="✅")

    @translate.error
    async def translate_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ) -> None:
        """Handle translate command errors."""
        log.tree("Translate Command Error", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Error", str(error)[:100]),
        ], emoji="❌")

        try:
            embed = discord.Embed(
                description="❌ An error occurred",
                color=COLOR_ERROR
            )
            set_footer(embed)

            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.HTTPException as e:
            log.tree("Translate Error Response Failed", [
                ("User", f"{interaction.user.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(TranslateCog(bot))
    log.tree("Command Loaded", [("Name", "translate")], emoji="✅")
