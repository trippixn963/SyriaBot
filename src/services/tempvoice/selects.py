"""
TempVoice - User Select Dropdowns
"""

from typing import TYPE_CHECKING

import discord
from discord import ui

from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING, COLOR_NEUTRAL, COLOR_BOOST
from src.core.config import config
from src.core.logger import log
from src.services.database import db
from src.utils.footer import set_footer
from .utils import (
    is_booster,
    generate_channel_name,
    MAX_ALLOWED_USERS_FREE,
    set_owner_permissions,
)

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
        self.message: discord.Message = None

    async def on_timeout(self):
        """Handle timeout - disable buttons and update message."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                embed = discord.Embed(description="⏳ Confirmation expired", color=COLOR_NEUTRAL)
                set_footer(embed)
                await self.message.edit(embed=embed, view=None)
            except discord.HTTPException:
                pass
        log.tree("Confirm View Expired", [
            ("Action", self.action),
            ("Channel", self.channel.name if self.channel else "Unknown"),
        ], emoji="⏳")

    @ui.button(label="Confirm", style=discord.ButtonStyle.secondary, emoji="<:allow:1455709499792031744>")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        self.confirmed = True
        self.stop()

        try:
            # Validate channel still exists
            channel = interaction.guild.get_channel(self.channel.id)
            if not channel:
                embed = discord.Embed(description="❌ Channel no longer exists", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
                log.tree("Confirm Failed", [
                    ("Action", self.action),
                    ("Channel ID", str(self.channel.id)),
                    ("Reason", "Channel deleted"),
                ], emoji="❌")
                return

            if self.action == "delete":
                channel_name = channel.name
                guild = interaction.guild
                db.delete_temp_channel(channel.id)
                await channel.delete(reason="Deleted by owner")
                embed = discord.Embed(description="🗑️ Channel deleted", color=COLOR_NEUTRAL)
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
                log.tree("Channel Deleted", [
                    ("Channel", channel_name),
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                ], emoji="🗑️")

                # Schedule reorder (debounced, non-blocking)
                if hasattr(interaction.client, 'tempvoice') and interaction.client.tempvoice:
                    interaction.client.tempvoice.schedule_reorder(guild)

            elif self.action == "transfer" and self.target:
                # Validate target still in guild
                target = interaction.guild.get_member(self.target.id)
                if not target:
                    embed = discord.Embed(description="❌ User no longer in server", color=COLOR_ERROR)
                    set_footer(embed)
                    await interaction.response.edit_message(embed=embed, view=None)
                    log.tree("Transfer Failed", [
                        ("Channel", channel.name),
                        ("Target", f"{self.target.name} ({self.target.display_name})"),
                        ("Target ID", str(self.target.id)),
                        ("Reason", "Target left server"),
                    ], emoji="❌")
                    return

                channel_info = db.get_temp_channel(channel.id)
                if not channel_info:
                    embed = discord.Embed(description="❌ Channel data not found", color=COLOR_ERROR)
                    set_footer(embed)
                    await interaction.response.edit_message(embed=embed, view=None)
                    log.tree("Transfer Failed", [
                        ("Channel", channel.name),
                        ("Reason", "No DB record"),
                    ], emoji="❌")
                    return

                old_owner = interaction.guild.get_member(channel_info["owner_id"])
                if old_owner:
                    await channel.set_permissions(old_owner, overwrite=None)
                await set_owner_permissions(channel, target)
                db.transfer_ownership(channel.id, target.id)

                # Generate channel name for new owner (uses shared utility)
                channel_name, name_source = generate_channel_name(target, interaction.guild)

                await channel.edit(name=channel_name)
                db.update_temp_channel(channel.id, name=channel_name)

                embed = discord.Embed(
                    description=f"🔄 Transferred to **{target.display_name}**\nChannel renamed to `{channel_name}`",
                    color=COLOR_SUCCESS
                )
                embed.set_thumbnail(url=target.display_avatar.url)
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
                log.tree("Channel Transferred", [
                    ("Channel", channel_name),
                    ("From", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("From ID", str(interaction.user.id)),
                    ("To", f"{target.name} ({target.display_name})"),
                    ("To ID", str(target.id)),
                ], emoji="🔄")

        except discord.HTTPException as e:
            log.tree("Confirm Action Failed", [
                ("Action", self.action),
                ("Channel", self.channel.name if self.channel else "Unknown"),
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("User ID", str(interaction.user.id)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description=f"❌ Failed: {e}", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
        except Exception as e:
            log.tree("Confirm Action Error", [
                ("Action", self.action),
                ("Channel", self.channel.name if self.channel else "Unknown"),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        self.stop()
        embed = discord.Embed(description="↩️ Cancelled", color=COLOR_NEUTRAL)
        set_footer(embed)
        await interaction.response.edit_message(embed=embed, view=None)
        log.tree("Action Cancelled", [
            ("Action", self.action),
            ("Channel", self.channel.name if self.channel else "Unknown"),
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("User ID", str(interaction.user.id)),
        ], emoji="↩️")


class UserSelectView(ui.View):
    """View for user selection actions."""

    def __init__(self, channel: discord.VoiceChannel, action: str, service: "TempVoiceService" = None):
        super().__init__(timeout=60)  # 60 second timeout
        self.channel = channel
        self.action = action
        self.service = service
        self.message: discord.Message = None
        self.add_item(UserSelect(channel, action, service))

    async def on_timeout(self):
        """Handle timeout - disable dropdown and update message."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                embed = discord.Embed(description="⏳ Selection expired", color=COLOR_NEUTRAL)
                set_footer(embed)
                await self.message.edit(embed=embed, view=None)
            except discord.HTTPException:
                pass
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
                embed = discord.Embed(description="❌ Channel no longer exists", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("User Select Failed", [
                    ("Action", self.action),
                    ("Channel ID", str(self.channel.id)),
                    ("Reason", "Channel deleted"),
                ], emoji="❌")
                return

            channel_info = db.get_temp_channel(channel.id)
            if not channel_info:
                embed = discord.Embed(description="❌ Channel not found", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
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
                ("User", f"{user.name} ({user.display_name})"),
                ("User ID", str(user.id)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to complete action", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            log.tree("User Select Error", [
                ("Action", self.action),
                ("User", f"{user.name} ({user.display_name})"),
                ("User ID", str(user.id)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _handle_permit(self, interaction: discord.Interaction, channel: discord.VoiceChannel, user: discord.Member, owner_id: int):
        """Handle permit/unpermit action."""
        if user.id == owner_id:
            embed = discord.Embed(description="⚠️ Can't permit yourself", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("Permit Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("User ID", str(user.id)),
                ("Reason", "Self-permit"),
            ], emoji="⚠️")
            return
        if user.bot:
            embed = discord.Embed(description="⚠️ Can't permit bots", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("Permit Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("User ID", str(user.id)),
                ("Reason", "Is bot"),
            ], emoji="⚠️")
            return

        # Check if user is already trusted (allow removing)
        current_trusted = db.get_trusted_list(owner_id)
        is_already_trusted = user.id in current_trusted

        # Check max allowed limit for non-boosters (only when adding, not removing)
        if not is_already_trusted and not is_booster(interaction.user):
            if len(current_trusted) >= MAX_ALLOWED_USERS_FREE:
                # Build list of currently allowed users
                allowed_list = []
                for uid in current_trusted[:5]:  # Show max 5
                    member = interaction.guild.get_member(uid)
                    if member:
                        allowed_list.append(f"• {member.mention}")
                    else:
                        allowed_list.append(f"• <@{uid}>")

                allowed_text = "\n".join(allowed_list) if allowed_list else "None"

                embed = discord.Embed(
                    title="💎 Booster Feature",
                    description="You've reached the limit for allowed users.",
                    color=COLOR_BOOST
                )
                embed.add_field(
                    name="📊 Your Usage",
                    value=f"`{len(current_trusted)}/{MAX_ALLOWED_USERS_FREE}` users allowed",
                    inline=True
                )
                embed.add_field(
                    name="🔊 Channel",
                    value=channel.mention,
                    inline=True
                )
                embed.add_field(
                    name="👥 Currently Allowed",
                    value=allowed_text,
                    inline=False
                )
                embed.add_field(
                    name="💎 Want Unlimited?",
                    value="**Boost the server** to unlock unlimited allowed users and custom channel names!",
                    inline=False
                )
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Permit Blocked", [
                    ("Channel", channel.name),
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("User ID", str(interaction.user.id)),
                    ("Reason", f"Max {MAX_ALLOWED_USERS_FREE} reached"),
                ], emoji="💎")
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
            embed = discord.Embed(
                description=f"✅ **{user.display_name}** added to allowed list\n`{total_allowed}` users allowed • Can access chat anytime",
                color=COLOR_SUCCESS
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("User Permitted", [
                ("Channel", channel.name),
                ("Target", f"{user.name} ({user.display_name})"),
                ("Target ID", str(user.id)),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("By ID", str(interaction.user.id)),
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
            embed = discord.Embed(
                description=f"❌ **{user.display_name}** removed from allowed list\n`{total_allowed}` users remaining",
                color=COLOR_ERROR
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("User Unpermitted", [
                ("Channel", channel.name),
                ("Target", f"{user.name} ({user.display_name})"),
                ("Target ID", str(user.id)),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("By ID", str(interaction.user.id)),
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
            embed = discord.Embed(description="⚠️ Can't block yourself", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("Block Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("User ID", str(user.id)),
                ("Reason", "Self-block"),
            ], emoji="⚠️")
            return
        if user.bot:
            embed = discord.Embed(description="⚠️ Can't block bots", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("Block Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("User ID", str(user.id)),
                ("Reason", "Is bot"),
            ], emoji="⚠️")
            return

        # Check if target is a mod - can only be blocked by developer
        is_target_mod = any(r.id == config.MOD_ROLE_ID for r in user.roles)
        if is_target_mod and owner_id != config.OWNER_ID:
            embed = discord.Embed(description="⚠️ Can't block moderators", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("Block Rejected", [
                ("Channel", channel.name),
                ("Target", f"{user.name} ({user.display_name})"),
                ("Target ID", str(user.id)),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("By ID", str(interaction.user.id)),
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
                        ("User", f"{user.name} ({user.display_name})"),
                        ("User ID", str(user.id)),
                        ("Error", str(e)),
                    ], emoji="❌")
            total_blocked = len(db.get_blocked_list(owner_id))
            embed = discord.Embed(
                description=f"🚫 **{user.display_name}** added to blocked list\n`{total_blocked}` users blocked",
                color=COLOR_ERROR
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("User Blocked", [
                ("Channel", channel.name),
                ("Target", f"{user.name} ({user.display_name})"),
                ("Target ID", str(user.id)),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("By ID", str(interaction.user.id)),
            ], emoji="🚫")
        else:
            # Already blocked - unblock them
            db.remove_blocked(owner_id, user.id)
            await channel.set_permissions(user, overwrite=None)
            total_blocked = len(db.get_blocked_list(owner_id))
            embed = discord.Embed(
                description=f"🔓 **{user.display_name}** removed from blocked list\n`{total_blocked}` users remaining",
                color=COLOR_SUCCESS
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("User Unblocked", [
                ("Channel", channel.name),
                ("Target", f"{user.name} ({user.display_name})"),
                ("Target ID", str(user.id)),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("By ID", str(interaction.user.id)),
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
            embed = discord.Embed(description="⚠️ Can't kick yourself", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("Kick Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("User ID", str(user.id)),
                ("Reason", "Self-kick"),
            ], emoji="⚠️")
            return

        # Protect moderators from being kicked
        if config.MOD_ROLE_ID and any(role.id == config.MOD_ROLE_ID for role in user.roles):
            embed = discord.Embed(description="⚠️ Can't kick moderators", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("Kick Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("User ID", str(user.id)),
                ("Reason", "Target is moderator"),
            ], emoji="⚠️")
            return

        if user.voice and user.voice.channel == channel:
            await user.move_to(None)
            embed = discord.Embed(
                description=f"👢 **{user.display_name}** kicked from channel",
                color=COLOR_ERROR
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("User Kicked", [
                ("Channel", channel.name),
                ("Target", f"{user.name} ({user.display_name})"),
                ("Target ID", str(user.id)),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("By ID", str(interaction.user.id)),
            ], emoji="👢")
        else:
            embed = discord.Embed(
                description=f"⚠️ **{user.display_name}** is not in channel",
                color=COLOR_WARNING
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("Kick Rejected", [
                ("Channel", channel.name),
                ("Target", f"{user.name} ({user.display_name})"),
                ("Target ID", str(user.id)),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("By ID", str(interaction.user.id)),
                ("Reason", "Not in channel"),
            ], emoji="⚠️")

    async def _handle_transfer(self, interaction: discord.Interaction, channel: discord.VoiceChannel, user: discord.Member, owner_id: int):
        """Handle transfer action."""
        if user.id == owner_id:
            embed = discord.Embed(description="⚠️ Already the owner", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("Transfer Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("User ID", str(user.id)),
                ("Reason", "Already owner"),
            ], emoji="⚠️")
            return
        if user.bot:
            embed = discord.Embed(description="⚠️ Can't transfer to bots", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree("Transfer Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("User ID", str(user.id)),
                ("Reason", "Is bot"),
            ], emoji="⚠️")
            return

        # Confirmation required
        embed = discord.Embed(
            description=f"🔄 Transfer **{channel.name}** to {user.mention}?",
            color=COLOR_WARNING,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        set_footer(embed)
        await interaction.response.send_message(embed=embed, view=ConfirmView("transfer", channel, user), ephemeral=True)
        log.tree("Transfer Confirmation Shown", [
            ("Channel", channel.name),
            ("Target", f"{user.name} ({user.display_name})"),
            ("Target ID", str(user.id)),
            ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("By ID", str(interaction.user.id)),
        ], emoji="🔄")
