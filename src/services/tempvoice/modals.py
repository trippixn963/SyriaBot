"""
SyriaBot - TempVoice Input Modals
=================================

Input modals for TempVoice channel customization.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import TYPE_CHECKING

import discord
from discord import ui

from src.core.config import config
from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING
from src.core.logger import logger
from src.services.database import db
from .utils import extract_base_name, build_full_name, get_channel_position

if TYPE_CHECKING:
    from .service import TempVoiceService


class NameModal(ui.Modal, title="Rename Channel"):
    """Modal for renaming the voice channel."""

    name_input = ui.TextInput(
        label="Channel Name (leave empty to reset)",
        placeholder="Enter new name or leave empty for auto-name",
        max_length=80,  # Leave room for numeral prefix
        required=False,
    )

    def __init__(self, channel: discord.VoiceChannel, member: discord.Member) -> None:
        super().__init__()
        self.channel = channel
        self.member = member
        # Show only base name in the input (without numeral prefix)
        channel_info = db.get_temp_channel(channel.id)
        base_name = channel_info.get("base_name") if channel_info else None
        if not base_name:
            base_name = extract_base_name(channel.name)
        self.name_input.default = base_name

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle channel rename submission."""
        logger.tree("Rename Modal Submitted", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Channel", self.channel.name),
            ("Input", self.name_input.value[:30] if self.name_input.value else "(empty)"),
        ], emoji="✏️")
        new_base_name = self.name_input.value.strip() if self.name_input.value else None

        # Defer first — channel.edit() can be slow (Discord rate limits renames)
        await interaction.response.defer(ephemeral=True)

        try:
            old_name = self.channel.name
            position = get_channel_position(self.channel)

            if new_base_name:
                # User provided a custom base name - build full name with numeral
                full_name = build_full_name(position, new_base_name)
                await self.channel.edit(name=full_name)

                db.update_temp_channel(self.channel.id, name=full_name, base_name=new_base_name)
                db.save_user_settings(interaction.user.id, default_name=new_base_name)
                embed = discord.Embed(
                    description=f"✏️ Renamed to **{full_name}**\n*Saved as default for future VCs*",
                    color=COLOR_SUCCESS
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.tree("Channel Renamed", [
                    ("From", old_name),
                    ("To", full_name),
                    ("Base Name", new_base_name),
                    ("Position", str(position)),
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                ], emoji="✏️")
            else:
                # Reset to auto-generated name (display name)
                display_name = self.member.display_name[:80]
                auto_name = build_full_name(position, display_name)

                await self.channel.edit(name=auto_name)

                db.update_temp_channel(self.channel.id, name=auto_name, base_name=display_name)
                # Clear saved default name
                db.save_user_settings(interaction.user.id, default_name=None)
                embed = discord.Embed(
                    description=f"🔄 Reset to **{auto_name}**\n*Future VCs will use auto-naming*",
                    color=COLOR_SUCCESS
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.tree("Channel Name Reset", [
                    ("From", old_name),
                    ("To", auto_name),
                    ("Base Name", display_name),
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                ], emoji="🔄")
        except discord.HTTPException as e:
            logger.error_tree("Channel Rename Failed", e, [
                ("Channel", self.channel.name),
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Status", str(e.status)),
            ])
            if e.status == 429:
                embed = discord.Embed(
                    description="⏳ Discord is rate limiting channel renames.\nPlease wait **a few minutes** and try again.",
                    color=COLOR_WARNING,
                )
            else:
                embed = discord.Embed(description="❌ Failed to rename channel", color=COLOR_ERROR)
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception:
                pass

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Handle modal errors — expired interactions are silently ignored."""
        if isinstance(error, discord.NotFound):
            logger.tree("Rename Modal Expired", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Channel", self.channel.name),
            ], emoji="⏳")
            return

        logger.error_tree("Rename Modal Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Channel", self.channel.name),
        ])
        try:
            embed = discord.Embed(description="❌ Failed to rename channel", color=COLOR_ERROR)
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


class LimitModal(ui.Modal, title="Set User Limit"):
    """Modal for setting user limit."""

    limit_input = ui.TextInput(
        label="User Limit",
        placeholder="Enter 0 for unlimited, or 1-99",
        max_length=2,
        required=True,
    )

    def __init__(self, channel: discord.VoiceChannel) -> None:
        super().__init__()
        self.channel = channel
        current = channel.user_limit
        self.limit_input.default = str(current) if current > 0 else "0"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle user limit submission."""
        logger.tree("Limit Modal Submitted", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Channel", self.channel.name),
            ("Input", self.limit_input.value),
        ], emoji="👥")

        # Validate input first (instant — can respond immediately)
        try:
            limit = int(self.limit_input.value)
        except ValueError:
            logger.tree("Limit Change Rejected", [
                ("Channel", self.channel.name),
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Input", self.limit_input.value),
                ("Reason", "Invalid number"),
            ], emoji="⚠️")
            embed = discord.Embed(description="⚠️ Enter a valid number", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if limit < 0 or limit > 99:
            embed = discord.Embed(description="⚠️ Must be 0-99", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Defer before channel.edit() which can be slow
        await interaction.response.defer(ephemeral=True)

        try:
            await self.channel.edit(user_limit=limit)
            db.update_temp_channel(self.channel.id, user_limit=limit)
            db.save_user_settings(interaction.user.id, default_limit=limit)
            limit_text = "unlimited" if limit == 0 else f"{limit} users"
            embed = discord.Embed(
                description=f"👥 Limit set to **{limit_text}**\n*Saved as default for future VCs*",
                color=COLOR_SUCCESS
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.tree("Limit Changed", [
                ("Channel", self.channel.name),
                ("Limit", limit_text),
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ], emoji="👥")
        except discord.HTTPException as e:
            logger.error_tree("Limit Change Failed", e, [
                ("Channel", self.channel.name),
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            embed = discord.Embed(description="❌ Failed to set limit", color=COLOR_ERROR)
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Handle modal errors — expired interactions are silently ignored."""
        if isinstance(error, discord.NotFound):
            logger.tree("Limit Modal Expired", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Channel", self.channel.name),
            ], emoji="⏳")
            return

        logger.error_tree("Limit Modal Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Channel", self.channel.name),
        ])
        try:
            embed = discord.Embed(description="❌ Failed to set limit", color=COLOR_ERROR)
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


class UserIdModal(ui.Modal, title="Enter User ID"):
    """Modal for searching a user by ID when the dropdown doesn't find them."""

    user_id_input = ui.TextInput(
        label="User ID",
        placeholder="Right-click user → Copy User ID",
        max_length=20,
        required=True,
    )

    def __init__(
        self,
        channel: discord.VoiceChannel,
        action: str,
        service: "TempVoiceService" = None,
    ) -> None:
        super().__init__()
        self.channel = channel
        self.action = action
        self.service = service

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.user_id_input.value.strip()

        try:
            user_id = int(raw)
        except ValueError:
            embed = discord.Embed(description="⚠️ Invalid ID — must be a number", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        member = interaction.guild.get_member(user_id)
        if not member:
            try:
                member = await interaction.guild.fetch_member(user_id)
            except discord.NotFound:
                embed = discord.Embed(description="❌ User not found in this server", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            except discord.HTTPException:
                embed = discord.Embed(description="❌ Failed to fetch user", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        # Validate channel still exists
        channel = interaction.guild.get_channel(self.channel.id)
        if not channel:
            embed = discord.Embed(description="❌ Channel no longer exists", color=COLOR_ERROR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        channel_info = db.get_temp_channel(channel.id)
        if not channel_info:
            embed = discord.Embed(description="❌ Channel not found", color=COLOR_ERROR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        owner_id = channel_info["owner_id"]

        # Route to the same handlers as UserSelect
        from .selects import UserSelect
        handler = UserSelect(channel, self.action, self.service)

        if self.action == "permit":
            await handler._handle_permit(interaction, channel, member, owner_id)
        elif self.action == "block":
            await handler._handle_block(interaction, channel, member, owner_id)
        elif self.action == "kick":
            await handler._handle_kick(interaction, channel, member, owner_id)
        elif self.action == "transfer":
            await handler._handle_transfer(interaction, channel, member, owner_id)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if isinstance(error, discord.NotFound):
            return
        logger.error_tree("UserID Modal Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("Action", self.action),
            ("Channel", self.channel.name),
        ])
        try:
            embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass
