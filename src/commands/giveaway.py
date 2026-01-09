"""
SyriaBot - Giveaway Command
===========================

Admin command to create and manage giveaways.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import config
from src.core.logger import log
from src.core.colors import COLOR_GOLD, COLOR_SUCCESS, COLOR_ERROR
from src.services.giveaway.views import GiveawaySetupView
from src.services.database import db
from src.utils.footer import set_footer


class GiveawayCog(commands.Cog):
    """Giveaway commands."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the cog."""
        self.bot: commands.Bot = bot

        # Register context menus (guild-specific to avoid global limit)
        guild = discord.Object(id=config.GUILD_ID)
        self.ctx_end = app_commands.ContextMenu(
            name="End Giveaway",
            callback=self.end_giveaway_ctx,
        )
        self.ctx_reroll = app_commands.ContextMenu(
            name="Reroll Winners",
            callback=self.reroll_giveaway_ctx,
        )
        self.ctx_cancel = app_commands.ContextMenu(
            name="Cancel Giveaway",
            callback=self.cancel_giveaway_ctx,
        )
        self.bot.tree.add_command(self.ctx_end, guild=guild)
        self.bot.tree.add_command(self.ctx_reroll, guild=guild)
        self.bot.tree.add_command(self.ctx_cancel, guild=guild)

    async def cog_unload(self) -> None:
        """Remove context menus when cog unloads."""
        guild = discord.Object(id=config.GUILD_ID)
        self.bot.tree.remove_command(self.ctx_end.name, type=self.ctx_end.type, guild=guild)
        self.bot.tree.remove_command(self.ctx_reroll.name, type=self.ctx_reroll.type, guild=guild)
        self.bot.tree.remove_command(self.ctx_cancel.name, type=self.ctx_cancel.type, guild=guild)

    def _is_admin(self, member: discord.Member) -> bool:
        """Check if user has admin permissions."""
        if member.guild_permissions.administrator:
            return True
        if member.guild_permissions.manage_guild:
            return True
        if config.MOD_ROLE_ID:
            mod_role = member.guild.get_role(config.MOD_ROLE_ID)
            if mod_role and mod_role in member.roles:
                return True
        return False

    async def _check_giveaway_message(
        self,
        interaction: discord.Interaction,
        message: discord.Message
    ) -> dict | None:
        """Check if message is a valid giveaway and user has permission."""
        # Check permissions
        if not self._is_admin(interaction.user):
            log.tree("Giveaway Action Denied", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Not admin"),
            ], emoji="🚫")
            await interaction.response.send_message(
                "You need admin permissions to manage giveaways.",
                ephemeral=True
            )
            return None

        # Check if service is available
        if not hasattr(self.bot, "giveaway_service") or not self.bot.giveaway_service:
            log.tree("Giveaway Action Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service not available"),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "Giveaway service not available.",
                ephemeral=True
            )
            return None

        # Check if this is a giveaway message
        giveaway = db.get_giveaway_by_message(message.id)
        if not giveaway:
            log.tree("Giveaway Not Found", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Message ID", str(message.id)),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "This doesn't appear to be a giveaway message.",
                ephemeral=True
            )
            return None

        return giveaway

    async def end_giveaway_ctx(self, interaction: discord.Interaction, message: discord.Message) -> None:
        """End a giveaway early (context menu)."""
        giveaway = await self._check_giveaway_message(interaction, message)
        if not giveaway:
            return

        if giveaway["ended"]:
            log.tree("Giveaway End Skipped", [
                ("Admin", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Giveaway ID", str(giveaway["id"])),
                ("Reason", "Already ended"),
            ], emoji="ℹ️")
            await interaction.response.send_message(
                "This giveaway has already ended.",
                ephemeral=True
            )
            return

        log.tree("Giveaway End (Manual)", [
            ("Admin", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Giveaway ID", str(giveaway["id"])),
        ], emoji="🏁")

        await interaction.response.defer(ephemeral=True)

        success, message_text, winners = await self.bot.giveaway_service.end_giveaway(giveaway["id"])

        if success:
            await interaction.followup.send(
                f"Giveaway ended! {len(winners)} winner(s) selected.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Failed to end giveaway: {message_text}",
                ephemeral=True
            )

    async def reroll_giveaway_ctx(self, interaction: discord.Interaction, message: discord.Message) -> None:
        """Reroll giveaway winners (context menu)."""
        giveaway = await self._check_giveaway_message(interaction, message)
        if not giveaway:
            return

        if not giveaway["ended"]:
            log.tree("Giveaway Reroll Skipped", [
                ("Admin", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Giveaway ID", str(giveaway["id"])),
                ("Reason", "Not ended yet"),
            ], emoji="ℹ️")
            await interaction.response.send_message(
                "This giveaway hasn't ended yet. End it first or wait for it to expire.",
                ephemeral=True
            )
            return

        log.tree("Giveaway Reroll", [
            ("Admin", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Giveaway ID", str(giveaway["id"])),
        ], emoji="🎲")

        await interaction.response.defer(ephemeral=True)

        success, message_text, winners = await self.bot.giveaway_service.reroll_giveaway(giveaway["id"])

        if success:
            await interaction.followup.send(
                f"Rerolled! New winner(s): {', '.join(f'<@{w}>' for w in winners)}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Failed to reroll: {message_text}",
                ephemeral=True
            )

    async def cancel_giveaway_ctx(self, interaction: discord.Interaction, message: discord.Message) -> None:
        """Cancel a giveaway (context menu)."""
        giveaway = await self._check_giveaway_message(interaction, message)
        if not giveaway:
            return

        if giveaway["ended"]:
            log.tree("Giveaway Cancel Skipped", [
                ("Admin", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Giveaway ID", str(giveaway["id"])),
                ("Reason", "Already ended"),
            ], emoji="ℹ️")
            await interaction.response.send_message(
                "This giveaway has already ended and cannot be cancelled.",
                ephemeral=True
            )
            return

        log.tree("Giveaway Cancel", [
            ("Admin", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Giveaway ID", str(giveaway["id"])),
        ], emoji="🗑️")

        await interaction.response.defer(ephemeral=True)

        success, message_text = await self.bot.giveaway_service.cancel_giveaway(giveaway["id"])

        if success:
            await interaction.followup.send(
                "Giveaway cancelled and deleted.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Failed to cancel: {message_text}",
                ephemeral=True
            )

    @app_commands.command(
        name="giveaway",
        description="Create a new giveaway (Admin only)"
    )
    @app_commands.guilds(discord.Object(id=config.GUILD_ID))
    async def giveaway(self, interaction: discord.Interaction) -> None:
        """Open giveaway setup builder."""
        log.tree("Giveaway Command", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ], emoji="🎉")

        # Check permissions
        if not self._is_admin(interaction.user):
            log.tree("Giveaway Command Denied", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Not admin"),
            ], emoji="🚫")
            await interaction.response.send_message(
                "You need admin permissions to create giveaways.",
                ephemeral=True
            )
            return

        # Check if service is enabled
        if not hasattr(self.bot, "giveaway_service") or not self.bot.giveaway_service:
            log.tree("Giveaway Command Blocked", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service not initialized"),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "Giveaway system is not enabled.",
                ephemeral=True
            )
            return

        # Create setup view
        view = GiveawaySetupView(self.bot.giveaway_service, interaction.user)
        embed = view.build_preview_embed()

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )

        # Store interaction for child views to update the original message
        view.set_original_interaction(interaction)

        log.tree("Giveaway Setup Started", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ], emoji="🔧")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(GiveawayCog(bot))
    log.tree("Command Loaded", [
        ("Name", "giveaway"),
    ], emoji="✅")
