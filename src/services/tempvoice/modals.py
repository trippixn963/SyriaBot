"""
TempVoice - Input Modals
"""

import discord
from discord import ui

from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING
from src.core.logger import log
from src.services.database import db
from src.services.webhook_logger import webhook_logger
from src.utils.footer import set_footer
from .utils import to_roman


class NameModal(ui.Modal, title="Rename Channel"):
    """Modal for renaming the voice channel."""

    name_input = ui.TextInput(
        label="Channel Name (leave empty to reset)",
        placeholder="Enter new name or leave empty for auto-name",
        max_length=100,
        required=False,
    )

    def __init__(self, channel: discord.VoiceChannel, member: discord.Member):
        super().__init__()
        self.channel = channel
        self.member = member
        self.name_input.default = channel.name

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name_input.value.strip() if self.name_input.value else None

        try:
            old_name = self.channel.name

            if new_name:
                # User provided a custom name
                await self.channel.edit(name=new_name)
                db.update_temp_channel(self.channel.id, name=new_name)
                db.save_user_settings(interaction.user.id, default_name=new_name)
                embed = discord.Embed(
                    description=f"✏️ Renamed to **{new_name}**\nThis will be your default name for future VCs",
                    color=COLOR_SUCCESS
                )
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Channel Renamed", [
                    ("From", old_name),
                    ("To", new_name),
                    ("By", str(interaction.user)),
                    ("Default Saved", "Yes"),
                ], emoji="✏️")

                # Webhook logging
                webhook_logger.log_tempvoice(interaction.user, "Rename", new_name)
            else:
                # Reset to auto-generated name
                existing_channels = db.get_all_temp_channels(interaction.guild.id)
                channel_num = len(existing_channels)
                roman = to_roman(max(1, channel_num))
                display_name = self.member.display_name[:80]
                auto_name = f"{roman}・{display_name}"

                await self.channel.edit(name=auto_name)
                db.update_temp_channel(self.channel.id, name=auto_name)
                # Clear saved default name
                db.save_user_settings(interaction.user.id, default_name=None)
                embed = discord.Embed(
                    description=f"🔄 Reset to **{auto_name}**\nFuture VCs will use auto-naming",
                    color=COLOR_SUCCESS
                )
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Channel Name Reset", [
                    ("From", old_name),
                    ("To", auto_name),
                    ("By", str(interaction.user)),
                    ("Default Cleared", "Yes"),
                ], emoji="🔄")

                # Webhook logging
                webhook_logger.log_tempvoice(interaction.user, "Name Reset", auto_name)
        except discord.HTTPException as e:
            log.tree("Channel Rename Failed", [
                ("Channel", self.channel.name),
                ("By", str(interaction.user)),
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

    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel
        current = channel.user_limit
        self.limit_input.default = str(current) if current > 0 else "0"

    async def on_submit(self, interaction: discord.Interaction):
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
                description=f"👥 Limit set to **{limit_text}**\nThis will be your default for future VCs",
                color=COLOR_SUCCESS
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("Limit Changed", [
                ("Channel", self.channel.name),
                ("Limit", limit_text),
                ("By", str(interaction.user)),
            ], emoji="👥")

            # Webhook logging
            webhook_logger.log_tempvoice(interaction.user, "Limit", self.channel.name, Limit=limit_text)
        except ValueError:
            log.tree("Limit Change Rejected", [
                ("Channel", self.channel.name),
                ("By", str(interaction.user)),
                ("Input", self.limit_input.value),
                ("Reason", "Invalid number"),
            ], emoji="⚠️")
            embed = discord.Embed(description="⚠️ Enter a valid number", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException as e:
            log.tree("Limit Change Failed", [
                ("Channel", self.channel.name),
                ("By", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            embed = discord.Embed(description="❌ Failed to set limit", color=COLOR_ERROR)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
