"""
TempVoice - User Select Dropdowns
"""

from typing import TYPE_CHECKING

import discord
from discord import ui

from src.core.config import config
from src.core.logger import log
from src.services.database import db

if TYPE_CHECKING:
    from .service import TempVoiceService


class ConfirmView(ui.View):
    """Confirmation view for destructive actions."""

    def __init__(self, action: str, channel: discord.VoiceChannel, target: discord.Member = None):
        super().__init__(timeout=60)  # 60 second timeout
        self.action = action
        self.channel = channel
        self.target = target
        self.confirmed = False

    async def on_timeout(self):
        """Handle timeout - cancel by default."""
        log.tree("Confirm View Expired", [
            ("Action", self.action),
            ("Channel", self.channel.name if self.channel else "Unknown"),
        ], emoji="⏳")

    @ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        self.confirmed = True
        self.stop()

        try:
            # Validate channel still exists
            channel = interaction.guild.get_channel(self.channel.id)
            if not channel:
                await interaction.response.edit_message(content="Channel no longer exists.", embed=None, view=None)
                log.tree("Confirm Failed", [
                    ("Action", self.action),
                    ("Channel ID", str(self.channel.id)),
                    ("Reason", "Channel deleted"),
                ], emoji="❌")
                return

            if self.action == "delete":
                channel_name = channel.name
                db.delete_temp_channel(channel.id)
                await channel.delete(reason="Deleted by owner")
                await interaction.response.edit_message(content="Channel deleted.", embed=None, view=None)
                log.tree("Channel Deleted", [
                    ("Channel", channel_name),
                    ("By", str(interaction.user)),
                ], emoji="🗑️")

            elif self.action == "transfer" and self.target:
                # Validate target still in guild
                target = interaction.guild.get_member(self.target.id)
                if not target:
                    await interaction.response.edit_message(content="User no longer in server.", embed=None, view=None)
                    log.tree("Transfer Failed", [
                        ("Channel", channel.name),
                        ("Target", str(self.target)),
                        ("Reason", "Target left server"),
                    ], emoji="❌")
                    return

                channel_info = db.get_temp_channel(channel.id)
                if not channel_info:
                    await interaction.response.edit_message(content="Channel data not found.", embed=None, view=None)
                    log.tree("Transfer Failed", [
                        ("Channel", channel.name),
                        ("Reason", "No DB record"),
                    ], emoji="❌")
                    return

                old_owner = interaction.guild.get_member(channel_info["owner_id"])
                if old_owner:
                    await channel.set_permissions(old_owner, overwrite=None)
                await channel.set_permissions(target, connect=True, manage_channels=True, move_members=True, send_messages=True, read_message_history=True)
                db.transfer_ownership(channel.id, target.id)
                await interaction.response.edit_message(content=f"Transferred to **{target.display_name}**.", embed=None, view=None)
                log.tree("Channel Transferred", [
                    ("Channel", channel.name),
                    ("From", str(interaction.user)),
                    ("To", str(target)),
                ], emoji="🔄")

        except discord.HTTPException as e:
            log.tree("Confirm Action Failed", [
                ("Action", self.action),
                ("Channel", self.channel.name if self.channel else "Unknown"),
                ("By", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                await interaction.response.edit_message(content=f"Failed: {e}", embed=None, view=None)
        except Exception as e:
            log.tree("Confirm Action Error", [
                ("Action", self.action),
                ("Channel", self.channel.name if self.channel else "Unknown"),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                await interaction.response.edit_message(content="An error occurred.", embed=None, view=None)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)
        log.tree("Action Cancelled", [
            ("Action", self.action),
            ("Channel", self.channel.name if self.channel else "Unknown"),
            ("By", str(interaction.user)),
        ], emoji="↩️")


class UserSelectView(ui.View):
    """View for user selection actions."""

    def __init__(self, channel: discord.VoiceChannel, action: str, service: "TempVoiceService" = None):
        super().__init__(timeout=60)  # 60 second timeout
        self.channel = channel
        self.action = action
        self.service = service
        self.add_item(UserSelect(channel, action, service))

    async def on_timeout(self):
        """Handle timeout."""
        log.tree("User Select Expired", [
            ("Action", self.action),
            ("Channel", self.channel.name if self.channel else "Unknown"),
        ], emoji="⏳")


class UserSelect(ui.UserSelect):
    """User select dropdown."""

    def __init__(self, channel: discord.VoiceChannel, action: str, service: "TempVoiceService" = None):
        placeholders = {
            "permit": "Select user to permit",
            "block": "Select user to block",
            "kick": "Select user to kick",
            "transfer": "Select new owner",
        }
        super().__init__(placeholder=placeholders.get(action, f"Select user"), min_values=1, max_values=1)
        self.channel = channel
        self.action = action
        self.service = service

    async def callback(self, interaction: discord.Interaction):
        user = self.values[0]

        try:
            # Validate channel still exists
            channel = interaction.guild.get_channel(self.channel.id)
            if not channel:
                await interaction.response.send_message("Channel no longer exists", ephemeral=True)
                log.tree("User Select Failed", [
                    ("Action", self.action),
                    ("Channel ID", str(self.channel.id)),
                    ("Reason", "Channel deleted"),
                ], emoji="❌")
                return

            channel_info = db.get_temp_channel(channel.id)
            if not channel_info:
                await interaction.response.send_message("Channel not found", ephemeral=True)
                log.tree("User Select Failed", [
                    ("Action", self.action),
                    ("Channel", channel.name),
                    ("Reason", "No DB record"),
                ], emoji="❌")
                return

            owner_id = channel_info["owner_id"]

            if self.action == "permit":
                await self._handle_permit(interaction, channel, user, owner_id)
            elif self.action == "block":
                await self._handle_block(interaction, channel, user, owner_id)
            elif self.action == "kick":
                await self._handle_kick(interaction, channel, user, owner_id)
            elif self.action == "transfer":
                await self._handle_transfer(interaction, channel, user, owner_id)

        except discord.HTTPException as e:
            log.tree("User Select Failed", [
                ("Action", self.action),
                ("User", str(user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                await interaction.response.send_message("Failed to complete action", ephemeral=True)
        except Exception as e:
            log.tree("User Select Error", [
                ("Action", self.action),
                ("User", str(user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                await interaction.response.send_message("An error occurred", ephemeral=True)

    async def _handle_permit(self, interaction: discord.Interaction, channel: discord.VoiceChannel, user: discord.Member, owner_id: int):
        """Handle permit/unpermit action."""
        if user.id == owner_id:
            await interaction.response.send_message("Can't permit yourself", ephemeral=True)
            log.tree("Permit Rejected", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("Reason", "Self-permit"),
            ], emoji="⚠️")
            return
        if user.bot:
            await interaction.response.send_message("Can't permit bots", ephemeral=True)
            log.tree("Permit Rejected", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("Reason", "Is bot"),
            ], emoji="⚠️")
            return

        # Remove from blocked if was blocked
        db.remove_blocked(owner_id, user.id)
        if db.add_trusted(owner_id, user.id):
            # Grant connect + permanent text access (even when not in VC)
            await channel.set_permissions(
                user,
                connect=True,
                send_messages=True,
                read_message_history=True
            )
            total_allowed = len(db.get_trusted_list(owner_id))
            await interaction.response.send_message(
                f"**{user.display_name}** added to allowed list (now {total_allowed} allowed)\nThey can now access chat even when not in the VC",
                ephemeral=True
            )
            log.tree("User Permitted", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("By", str(interaction.user)),
                ("Total Allowed", str(total_allowed)),
                ("Text Access", "Granted"),
            ], emoji="✅")
        else:
            # Already permitted - remove them
            db.remove_trusted(owner_id, user.id)
            # Revoke text access unless they're currently in the channel
            if user.voice and user.voice.channel == channel:
                # In channel - keep text access, just remove trusted connect
                overwrites = channel.overwrites_for(user)
                overwrites.connect = None
                await channel.set_permissions(user, overwrite=overwrites)
                text_status = "Kept (in VC)"
            else:
                # Not in channel - revoke all permissions
                await channel.set_permissions(user, overwrite=None)
                text_status = "Revoked"
            total_allowed = len(db.get_trusted_list(owner_id))
            await interaction.response.send_message(
                f"**{user.display_name}** removed from allowed list ({total_allowed} remaining)",
                ephemeral=True
            )
            log.tree("User Unpermitted", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("By", str(interaction.user)),
                ("Total Allowed", str(total_allowed)),
                ("Text Access", text_status),
            ], emoji="❌")

        # Update panel to reflect new counts
        if self.service:
            try:
                await self.service._update_panel(channel)
            except Exception as e:
                log.tree("Panel Update Failed", [
                    ("Channel", channel.name),
                    ("Context", "After permit"),
                    ("Error", str(e)),
                ], emoji="⚠️")

    async def _handle_block(self, interaction: discord.Interaction, channel: discord.VoiceChannel, user: discord.Member, owner_id: int):
        """Handle block/unblock action."""
        if user.id == owner_id:
            await interaction.response.send_message("Can't block yourself", ephemeral=True)
            log.tree("Block Rejected", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("Reason", "Self-block"),
            ], emoji="⚠️")
            return
        if user.bot:
            await interaction.response.send_message("Can't block bots", ephemeral=True)
            log.tree("Block Rejected", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("Reason", "Is bot"),
            ], emoji="⚠️")
            return

        # Check if target is a mod - can only be blocked by developer
        is_target_mod = any(r.id == config.MOD_ROLE_ID for r in user.roles)
        if is_target_mod and owner_id != config.OWNER_ID:
            await interaction.response.send_message("Can't block moderators", ephemeral=True)
            log.tree("Block Rejected", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("By", str(interaction.user)),
                ("Reason", "Target is moderator"),
            ], emoji="⚠️")
            return

        # Remove from trusted if was trusted
        db.remove_trusted(owner_id, user.id)
        if db.add_blocked(owner_id, user.id):
            await channel.set_permissions(user, connect=False)
            if user.voice and user.voice.channel == channel:
                try:
                    await user.move_to(None)
                except discord.HTTPException as e:
                    log.tree("Blocked User Disconnect Failed", [
                        ("Channel", channel.name),
                        ("User", str(user)),
                        ("Error", str(e)),
                    ], emoji="❌")
            total_blocked = len(db.get_blocked_list(owner_id))
            await interaction.response.send_message(
                f"**{user.display_name}** added to blocked list (now {total_blocked} blocked)",
                ephemeral=True
            )
            log.tree("User Blocked", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("By", str(interaction.user)),
                ("Total Blocked", str(total_blocked)),
            ], emoji="🚫")
        else:
            # Already blocked - unblock them
            db.remove_blocked(owner_id, user.id)
            await channel.set_permissions(user, overwrite=None)
            total_blocked = len(db.get_blocked_list(owner_id))
            await interaction.response.send_message(
                f"**{user.display_name}** removed from blocked list ({total_blocked} remaining)",
                ephemeral=True
            )
            log.tree("User Unblocked", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("By", str(interaction.user)),
                ("Total Blocked", str(total_blocked)),
            ], emoji="🔓")

        # Update panel to reflect new counts
        if self.service:
            try:
                await self.service._update_panel(channel)
            except Exception as e:
                log.tree("Panel Update Failed", [
                    ("Channel", channel.name),
                    ("Context", "After block"),
                    ("Error", str(e)),
                ], emoji="⚠️")

    async def _handle_kick(self, interaction: discord.Interaction, channel: discord.VoiceChannel, user: discord.Member, owner_id: int):
        """Handle kick action."""
        if user.id == owner_id:
            await interaction.response.send_message("Can't kick yourself", ephemeral=True)
            log.tree("Kick Rejected", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("Reason", "Self-kick"),
            ], emoji="⚠️")
            return

        if user.voice and user.voice.channel == channel:
            await user.move_to(None)
            await interaction.response.send_message(f"**{user.display_name}** kicked", ephemeral=True)
            log.tree("User Kicked", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("By", str(interaction.user)),
            ], emoji="👢")
        else:
            await interaction.response.send_message(f"**{user.display_name}** not in channel", ephemeral=True)
            log.tree("Kick Rejected", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("By", str(interaction.user)),
                ("Reason", "Not in channel"),
            ], emoji="⚠️")

    async def _handle_transfer(self, interaction: discord.Interaction, channel: discord.VoiceChannel, user: discord.Member, owner_id: int):
        """Handle transfer action."""
        if user.id == owner_id:
            await interaction.response.send_message("Already owner", ephemeral=True)
            log.tree("Transfer Rejected", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("Reason", "Already owner"),
            ], emoji="⚠️")
            return
        if user.bot:
            await interaction.response.send_message("Can't transfer to bot", ephemeral=True)
            log.tree("Transfer Rejected", [
                ("Channel", channel.name),
                ("User", str(user)),
                ("Reason", "Is bot"),
            ], emoji="⚠️")
            return

        # Confirmation required
        embed = discord.Embed(
            description=f"Transfer **{channel.name}** to {user.mention}?",
            color=0xf04747,
        )
        await interaction.response.send_message(embed=embed, view=ConfirmView("transfer", channel, user), ephemeral=True)
        log.tree("Transfer Confirmation Shown", [
            ("Channel", channel.name),
            ("Target", str(user)),
            ("By", str(interaction.user)),
        ], emoji="🔄")
