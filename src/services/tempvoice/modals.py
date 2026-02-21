"""
SyriaBot - TempVoice Input Modals
=================================

Input modals for TempVoice channel customization.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import ui

from src.core.config import config
from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING
from src.core.logger import logger
from src.services.database import db
from src.utils.footer import set_footer
from .utils import extract_base_name, build_full_name


def _get_channel_position(channel: discord.VoiceChannel) -> int:
    """Get a channel's position number based on its position in the category."""
    if not channel.category:
        return 1

    # Get all temp voice channels in category, sorted by position
    voice_channels = sorted(
        [ch for ch in channel.category.voice_channels
         if ch.id != config.VC_CREATOR_CHANNEL_ID and db.is_temp_channel(ch.id)],
        key=lambda c: c.position
    )

    # Find this channel's position (1-indexed)
    for idx, ch in enumerate(voice_channels, start=1):
        if ch.id == channel.id:
            return idx

    return 1  # Fallback


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

        try:
            old_name = self.channel.name
            position = _get_channel_position(self.channel)

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
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
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
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.tree("Channel Name Reset", [
                    ("From", old_name),
                    ("To", auto_name),
                    ("Base Name", display_name),
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                ], emoji="🔄")
        except discord.HTTPException as e:
            logger.tree("Channel Rename Failed", [
                ("Channel", self.channel.name),
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Error", str(e)),
            ], emoji="❌")
            embed = discord.Embed(description="❌ Failed to rename channel", color=COLOR_ERROR)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)


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
        try:
            limit = int(self.limit_input.value)
            if limit < 0 or limit > 99:
                embed = discord.Embed(description="⚠️ Must be 0-99", color=COLOR_WARNING)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            await self.channel.edit(user_limit=limit)
            db.update_temp_channel(self.channel.id, user_limit=limit)
            db.save_user_settings(interaction.user.id, default_limit=limit)
            limit_text = "unlimited" if limit == 0 else f"{limit} users"
            embed = discord.Embed(
                description=f"👥 Limit set to **{limit_text}**\n*Saved as default for future VCs*",
                color=COLOR_SUCCESS
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("Limit Changed", [
                ("Channel", self.channel.name),
                ("Limit", limit_text),
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ], emoji="👥")
        except ValueError:
            logger.tree("Limit Change Rejected", [
                ("Channel", self.channel.name),
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Input", self.limit_input.value),
                ("Reason", "Invalid number"),
            ], emoji="⚠️")
            embed = discord.Embed(description="⚠️ Enter a valid number", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException as e:
            logger.tree("Limit Change Failed", [
                ("Channel", self.channel.name),
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Error", str(e)),
            ], emoji="❌")
            embed = discord.Embed(description="❌ Failed to set limit", color=COLOR_ERROR)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
