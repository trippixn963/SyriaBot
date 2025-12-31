"""
SyriaBot - TempVoice Service
============================

Temporary voice channel management with control panel.

Author: حَـــــنَّـــــا
"""

import asyncio
import time

import discord
from discord import ui
from typing import TYPE_CHECKING, Optional, List, Dict

from src.core.config import config
from src.core.logger import log
from src.services.database import db
from src.utils.footer import set_footer

if TYPE_CHECKING:
    from src.bot import SyriaBot


# Cooldown between join-to-create attempts (seconds)
JOIN_COOLDOWN = 5


# =============================================================================
# Helpers
# =============================================================================

def to_roman(num: int) -> str:
    """Convert integer to Roman numeral."""
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    result = ""
    for i, v in enumerate(val):
        while num >= v:
            result += syms[i]
            num -= v
    return result


# =============================================================================
# Modals
# =============================================================================

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
                await interaction.response.send_message(
                    f"Renamed to **{new_name}**\nThis will be your default name for future VCs.",
                    ephemeral=True
                )
                log.tree("Channel Renamed", [
                    ("From", old_name),
                    ("To", new_name),
                    ("By", str(interaction.user)),
                    ("Default Saved", "Yes"),
                ], emoji="✏️")
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
                await interaction.response.send_message(
                    f"Reset to **{auto_name}**\nFuture VCs will use auto-naming.",
                    ephemeral=True
                )
                log.tree("Channel Name Reset", [
                    ("From", old_name),
                    ("To", auto_name),
                    ("By", str(interaction.user)),
                    ("Default Cleared", "Yes"),
                ], emoji="🔄")
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True)


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
                await interaction.response.send_message("Must be 0-99", ephemeral=True)
                return
            await self.channel.edit(user_limit=limit)
            db.update_temp_channel(self.channel.id, user_limit=limit)
            db.save_user_settings(interaction.user.id, default_limit=limit)
            limit_text = "**unlimited**" if limit == 0 else f"**{limit} users**"
            await interaction.response.send_message(f"Limit set to {limit_text}\nThis will be your default for future VCs.", ephemeral=True)
            log.tree("Limit Changed", [
                ("Channel", self.channel.name),
                ("Limit", limit_text),
                ("By", str(interaction.user)),
            ], emoji="👥")
        except ValueError:
            await interaction.response.send_message("Enter a valid number", ephemeral=True)


# =============================================================================
# User Select Views
# =============================================================================

class ConfirmView(ui.View):
    """Confirmation view for destructive actions."""

    def __init__(self, action: str, channel: discord.VoiceChannel, target: discord.Member = None):
        super().__init__(timeout=None)
        self.action = action
        self.channel = channel
        self.target = target
        self.confirmed = False

    @ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        self.confirmed = True
        self.stop()

        # Validate channel still exists
        channel = interaction.guild.get_channel(self.channel.id)
        if not channel:
            await interaction.response.edit_message(content="Channel no longer exists.", embed=None, view=None)
            return

        if self.action == "delete":
            channel_name = channel.name
            try:
                db.delete_temp_channel(channel.id)
                await channel.delete(reason="Deleted by owner")
                await interaction.response.edit_message(content="Channel deleted.", embed=None, view=None)
                log.tree("Channel Deleted", [
                    ("Channel", channel_name),
                    ("By", str(interaction.user)),
                ], emoji="🗑️")
            except discord.HTTPException as e:
                log.tree("Channel Delete Failed", [
                    ("Channel", channel_name),
                    ("By", str(interaction.user)),
                    ("Error", str(e)),
                ], emoji="❌")
                await interaction.response.edit_message(content="Failed to delete channel.", embed=None, view=None)

        elif self.action == "transfer" and self.target:
            # Validate target still in guild
            target = interaction.guild.get_member(self.target.id)
            if not target:
                await interaction.response.edit_message(content="User no longer in server.", embed=None, view=None)
                return

            channel_info = db.get_temp_channel(channel.id)
            if not channel_info:
                await interaction.response.edit_message(content="Channel data not found.", embed=None, view=None)
                return

            try:
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
                log.tree("Channel Transfer Failed", [
                    ("Channel", channel.name),
                    ("From", str(interaction.user)),
                    ("To", str(target)),
                    ("Error", str(e)),
                ], emoji="❌")
                await interaction.response.edit_message(content="Failed to transfer channel.", embed=None, view=None)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)


class UserSelectView(ui.View):
    """View for user selection actions."""

    def __init__(self, channel: discord.VoiceChannel, action: str, service: "TempVoiceService" = None):
        super().__init__(timeout=None)
        self.channel = channel
        self.action = action
        self.service = service
        self.add_item(UserSelect(channel, action, service))


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

        # Validate channel still exists
        channel = interaction.guild.get_channel(self.channel.id)
        if not channel:
            await interaction.response.send_message("Channel no longer exists", ephemeral=True)
            return

        channel_info = db.get_temp_channel(channel.id)
        if not channel_info:
            await interaction.response.send_message("Channel not found", ephemeral=True)
            return

        owner_id = channel_info["owner_id"]

        if self.action == "permit":
            if user.id == owner_id:
                await interaction.response.send_message("Can't permit yourself", ephemeral=True)
                return
            if user.bot:
                await interaction.response.send_message("Can't permit bots", ephemeral=True)
                return

            try:
                # Remove from blocked if was blocked
                db.remove_blocked(owner_id, user.id)
                if db.add_trusted(owner_id, user.id):
                    await channel.set_permissions(user, connect=True)
                    total_allowed = len(db.get_trusted_list(owner_id))
                    await interaction.response.send_message(
                        f"**{user.display_name}** added to allowed list (now {total_allowed} allowed)",
                        ephemeral=True
                    )
                    log.tree("User Permitted", [
                        ("Channel", channel.name),
                        ("User", str(user)),
                        ("By", str(interaction.user)),
                        ("Total Allowed", str(total_allowed)),
                    ], emoji="✅")
                else:
                    # Already permitted - remove them
                    db.remove_trusted(owner_id, user.id)
                    # Only remove overwrite if not in channel (preserve text access if in channel)
                    if not (user.voice and user.voice.channel == channel):
                        await channel.set_permissions(user, overwrite=None)
                    else:
                        # In channel - just remove connect, keep text
                        overwrites = channel.overwrites_for(user)
                        overwrites.connect = None
                        await channel.set_permissions(user, overwrite=overwrites)
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
                    ], emoji="❌")
            except discord.HTTPException as e:
                log.tree("Permit Failed", [
                    ("Channel", channel.name),
                    ("User", str(user)),
                    ("By", str(interaction.user)),
                    ("Error", str(e)),
                ], emoji="❌")
                if not interaction.response.is_done():
                    await interaction.response.send_message("Failed to update permissions", ephemeral=True)
                return

            # Update panel to reflect new counts
            if self.service:
                try:
                    await self.service._update_panel(channel)
                except Exception:
                    pass

        elif self.action == "block":
            if user.id == owner_id:
                await interaction.response.send_message("Can't block yourself", ephemeral=True)
                return
            if user.bot:
                await interaction.response.send_message("Can't block bots", ephemeral=True)
                return

            # Check if target is a mod - can only be blocked by developer
            is_target_mod = any(r.id == config.MOD_ROLE_ID for r in user.roles)
            if is_target_mod and owner_id != config.OWNER_ID:
                await interaction.response.send_message("Can't block moderators", ephemeral=True)
                return

            try:
                # Remove from trusted if was trusted
                db.remove_trusted(owner_id, user.id)
                if db.add_blocked(owner_id, user.id):
                    await channel.set_permissions(user, connect=False)
                    if user.voice and user.voice.channel == channel:
                        try:
                            await user.move_to(None)
                        except discord.HTTPException:
                            pass  # May fail if user left already
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
            except discord.HTTPException as e:
                log.tree("Block Failed", [
                    ("Channel", channel.name),
                    ("User", str(user)),
                    ("By", str(interaction.user)),
                    ("Error", str(e)),
                ], emoji="❌")
                if not interaction.response.is_done():
                    await interaction.response.send_message("Failed to update permissions", ephemeral=True)
                return

            # Update panel to reflect new counts
            if self.service:
                try:
                    await self.service._update_panel(channel)
                except Exception:
                    pass

        elif self.action == "kick":
            if user.id == owner_id:
                await interaction.response.send_message("Can't kick yourself", ephemeral=True)
                return
            if user.voice and user.voice.channel == channel:
                try:
                    await user.move_to(None)
                    await interaction.response.send_message(f"**{user.display_name}** kicked", ephemeral=True)
                    log.tree("User Kicked", [
                        ("Channel", channel.name),
                        ("User", str(user)),
                        ("By", str(interaction.user)),
                    ], emoji="👢")
                except discord.HTTPException as e:
                    log.tree("Kick Failed", [
                        ("Channel", channel.name),
                        ("User", str(user)),
                        ("By", str(interaction.user)),
                        ("Error", str(e)),
                    ], emoji="❌")
                    await interaction.response.send_message("Failed to kick user", ephemeral=True)
            else:
                await interaction.response.send_message(f"**{user.display_name}** not in channel", ephemeral=True)

        elif self.action == "transfer":
            if user.id == owner_id:
                await interaction.response.send_message("Already owner", ephemeral=True)
                return
            if user.bot:
                await interaction.response.send_message("Can't transfer to bot", ephemeral=True)
                return
            # Confirmation required
            embed = discord.Embed(
                description=f"Transfer **{channel.name}** to {user.mention}?",
                color=0xf04747,
            )
            await interaction.response.send_message(embed=embed, view=ConfirmView("transfer", channel, user), ephemeral=True)


# =============================================================================
# Control Panel
# =============================================================================

class TempVoiceControlPanel(ui.View):
    """Control panel for temp voice channels."""

    def __init__(self, service: "TempVoiceService"):
        super().__init__(timeout=None)
        self.service = service

    async def _get_user_channel(self, interaction: discord.Interaction) -> Optional[discord.VoiceChannel]:
        """Get the user's temp voice channel."""
        channel_id = db.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            await interaction.response.send_message("You don't own a channel", ephemeral=True)
            return None

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            db.delete_temp_channel(channel_id)
            await interaction.response.send_message("Channel no longer exists", ephemeral=True)
            return None

        return channel

    # Row 1: Lock, Limit, Rename
    @ui.button(label="Locked", emoji="<:lock:1455709111684694107>", style=discord.ButtonStyle.secondary, custom_id="tv_lock", row=0)
    async def lock_button(self, interaction: discord.Interaction, button: ui.Button):
        """Toggle lock/unlock."""
        try:
            # Check ownership first (before deferring)
            channel_id = db.get_owner_channel(interaction.user.id, interaction.guild.id)
            if not channel_id:
                await interaction.response.send_message("You don't own a channel", ephemeral=True)
                return

            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                db.delete_temp_channel(channel_id)
                await interaction.response.send_message("Channel no longer exists", ephemeral=True)
                return

            channel_info = db.get_temp_channel(channel.id)
            if not channel_info:
                await interaction.response.send_message("Channel data not found", ephemeral=True)
                return

            is_locked = channel_info.get("is_locked", 0)
            new_locked = 0 if is_locked else 1
            everyone = interaction.guild.default_role

            # Send response first, then do the work
            if new_locked:
                await interaction.response.send_message("<:lock:1455709111684694107> Channel is now **locked**", ephemeral=True)
                await channel.set_permissions(everyone, connect=False, send_messages=False, read_message_history=False)
            else:
                await interaction.response.send_message("<:unlock:1455709112309514290> Channel is now **unlocked**", ephemeral=True)
                await channel.set_permissions(everyone, connect=True, send_messages=False, read_message_history=False)

            db.update_temp_channel(channel.id, is_locked=new_locked)
            log.tree("Lock Toggled", [
                ("Channel", channel.name),
                ("Status", "Locked" if new_locked else "Unlocked"),
                ("By", str(interaction.user)),
            ], emoji="🔒" if new_locked else "🔓")

            # Update panel to reflect new state
            try:
                await self.service._update_panel(channel)
            except Exception:
                pass  # Panel update is non-critical
        except Exception as e:
            log.tree("Lock Toggle Failed", [
                ("By", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                await interaction.response.send_message("An error occurred", ephemeral=True)

    @ui.button(label="Limit", emoji="<:limit:1455709299732123762>", style=discord.ButtonStyle.secondary, custom_id="tv_limit", row=0)
    async def limit_button(self, interaction: discord.Interaction, button: ui.Button):
        """Set user limit."""
        channel = await self._get_user_channel(interaction)
        if channel:
            await interaction.response.send_modal(LimitModal(channel))

    @ui.button(label="Rename", emoji="<:rename:1455709387711578394>", style=discord.ButtonStyle.secondary, custom_id="tv_rename", row=0)
    async def rename_button(self, interaction: discord.Interaction, button: ui.Button):
        """Rename channel."""
        channel = await self._get_user_channel(interaction)
        if channel:
            await interaction.response.send_modal(NameModal(channel, interaction.user))

    # Row 2: Permit, Block, Kick
    @ui.button(label="Allow", emoji="<:allow:1455709499792031744>", style=discord.ButtonStyle.secondary, custom_id="tv_permit", row=1)
    async def permit_button(self, interaction: discord.Interaction, button: ui.Button):
        """Permit/unpermit a user."""
        channel = await self._get_user_channel(interaction)
        if channel:
            await interaction.response.send_message("Select user (select again to remove):", view=UserSelectView(channel, "permit", self.service), ephemeral=True)

    @ui.button(label="Block", emoji="<:block:1455709662316986539>", style=discord.ButtonStyle.secondary, custom_id="tv_block", row=1)
    async def block_button(self, interaction: discord.Interaction, button: ui.Button):
        """Block/unblock a user."""
        channel = await self._get_user_channel(interaction)
        if channel:
            await interaction.response.send_message("Select user (select again to unblock):", view=UserSelectView(channel, "block", self.service), ephemeral=True)

    @ui.button(label="Kick", emoji="<:kick:1455709879976198361>", style=discord.ButtonStyle.secondary, custom_id="tv_kick", row=1)
    async def kick_button(self, interaction: discord.Interaction, button: ui.Button):
        """Kick a user."""
        channel = await self._get_user_channel(interaction)
        if channel:
            await interaction.response.send_message("Select user to kick:", view=UserSelectView(channel, "kick"), ephemeral=True)

    # Row 3: Claim, Transfer, Delete
    @ui.button(label="Claim", emoji="<:claim:1455709985467011173>", style=discord.ButtonStyle.secondary, custom_id="tv_claim", row=2)
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        """Claim abandoned channel."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("Join a voice channel first", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        channel_info = db.get_temp_channel(channel.id)

        if not channel_info:
            await interaction.response.send_message("Not a temp channel", ephemeral=True)
            return

        owner_id = channel_info["owner_id"]
        owner = interaction.guild.get_member(owner_id)
        owner_in_channel = any(m.id == owner_id for m in channel.members)

        if owner_in_channel:
            owner_name = owner.display_name if owner else "The owner"
            await interaction.response.send_message(f"{owner_name} is still in the channel", ephemeral=True)
            return

        existing = db.get_owner_channel(interaction.user.id, interaction.guild.id)
        if existing:
            await interaction.response.send_message("You already own a channel", ephemeral=True)
            return

        # Show who the previous owner was
        prev_owner_text = owner.mention if owner else f"User ID {owner_id}"

        # Give new owner full permissions
        await channel.set_permissions(interaction.user, connect=True, manage_channels=True, move_members=True, send_messages=True, read_message_history=True)
        db.transfer_ownership(channel.id, interaction.user.id)
        await interaction.response.send_message(
            f"You now own **{channel.name}**\nPrevious owner: {prev_owner_text}",
            ephemeral=True
        )
        log.tree("Channel Claimed", [
            ("Channel", channel.name),
            ("New Owner", str(interaction.user)),
            ("Previous Owner", str(owner) if owner else str(owner_id)),
        ], emoji="👑")

        # Update panel to reflect new owner
        if self.service:
            try:
                await self.service._update_panel(channel)
            except Exception:
                pass

    @ui.button(label="Transfer", emoji="<:transfer:1455710226429902858>", style=discord.ButtonStyle.secondary, custom_id="tv_transfer", row=2)
    async def transfer_button(self, interaction: discord.Interaction, button: ui.Button):
        """Transfer ownership."""
        channel = await self._get_user_channel(interaction)
        if channel:
            await interaction.response.send_message("Select new owner:", view=UserSelectView(channel, "transfer"), ephemeral=True)

    @ui.button(label="Delete", emoji="<:delete:1455710362539397192>", style=discord.ButtonStyle.secondary, custom_id="tv_delete", row=2)
    async def delete_button(self, interaction: discord.Interaction, button: ui.Button):
        """Delete channel."""
        channel = await self._get_user_channel(interaction)
        if not channel:
            return

        # Count members that will be disconnected (excluding self)
        other_members = [m for m in channel.members if m.id != interaction.user.id]
        member_count = len(other_members)

        if member_count > 0:
            desc = f"Delete **{channel.name}**?\n⚠️ {member_count} member{'s' if member_count != 1 else ''} will be disconnected."
        else:
            desc = f"Delete **{channel.name}**?"

        embed = discord.Embed(
            description=desc,
            color=0xf04747,
        )
        await interaction.response.send_message(embed=embed, view=ConfirmView("delete", channel), ephemeral=True)


# =============================================================================
# TempVoice Service
# =============================================================================

class TempVoiceService:
    """Service for managing temporary voice channels."""

    def __init__(self, bot: "SyriaBot"):
        self.bot = bot
        self.control_panel = TempVoiceControlPanel(self)
        self._cleanup_task: asyncio.Task = None
        self._join_cooldowns: Dict[int, float] = {}  # user_id -> last join timestamp

    async def setup(self) -> None:
        """Set up the TempVoice service."""
        # Validate config
        warnings = []
        if not config.VC_CREATOR_CHANNEL_ID:
            warnings.append("VC_CREATOR_CHANNEL_ID not set - join-to-create disabled")
        if not config.VC_CATEGORY_ID:
            warnings.append("VC_CATEGORY_ID not set - VCs will be created without category")
        if not config.MOD_ROLE_ID:
            warnings.append("MOD_ROLE_ID not set - mod permissions disabled")

        if warnings:
            log.tree("TempVoice Config Warnings", [
                (f"⚠️ {i+1}", w) for i, w in enumerate(warnings)
            ], emoji="⚠️")

        self.bot.add_view(self.control_panel)
        await self._cleanup_orphaned_channels()
        await self._cleanup_empty_channels()  # Initial cleanup

        # Start periodic cleanup task
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

        cleanup_mins = config.VC_CLEANUP_INTERVAL // 60
        log.tree("TempVoice Service", [
            ("Status", "Initialized"),
            ("Creator Channel", str(config.VC_CREATOR_CHANNEL_ID) if config.VC_CREATOR_CHANNEL_ID else "Not set"),
            ("Category", str(config.VC_CATEGORY_ID) if config.VC_CATEGORY_ID else "Not set"),
            ("Mod Role", str(config.MOD_ROLE_ID) if config.MOD_ROLE_ID else "Not set"),
            ("Cleanup Interval", f"{cleanup_mins} minutes"),
        ], emoji="🔊")

    async def stop(self) -> None:
        """Stop the TempVoice service."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        log.tree("TempVoice Service", [
            ("Status", "Stopped"),
        ], emoji="🔇")

    async def _periodic_cleanup(self) -> None:
        """Periodically clean up empty temp channels."""
        while True:
            await asyncio.sleep(config.VC_CLEANUP_INTERVAL)
            try:
                await self._cleanup_empty_channels()
            except Exception as e:
                log.tree("Periodic Cleanup Failed", [
                    ("Error", str(e)),
                ], emoji="❌")

    async def _cleanup_empty_channels(self) -> None:
        """Scan and delete empty temp channels (handles missed deletions)."""
        channels = db.get_all_temp_channels()
        cleaned = 0

        # Build protected set: creator channel + any configured protected channels
        protected = set(config.VC_PROTECTED_CHANNELS)
        if config.VC_CREATOR_CHANNEL_ID:
            protected.add(config.VC_CREATOR_CHANNEL_ID)

        for channel_data in channels:
            channel_id = channel_data["channel_id"]

            # Skip protected channels
            if channel_id in protected:
                continue

            channel = self.bot.get_channel(channel_id)

            # Channel doesn't exist in Discord - clean up DB
            if not channel:
                db.delete_temp_channel(channel_id)
                cleaned += 1
                continue

            # Channel exists but is empty - delete it
            if len(channel.members) == 0:
                try:
                    channel_name = channel.name
                    db.delete_temp_channel(channel_id)
                    await channel.delete(reason="Empty channel cleanup")
                    cleaned += 1
                    log.tree("Empty Channel Cleaned", [
                        ("Channel", channel_name),
                        ("Reason", "Periodic cleanup"),
                    ], emoji="🧹")
                except discord.HTTPException:
                    pass

        if cleaned > 0:
            log.tree("Periodic Cleanup Complete", [
                ("Channels Removed", str(cleaned)),
            ], emoji="🧹")

    async def _cleanup_orphaned_channels(self) -> None:
        """Clean up temp channels that no longer exist."""
        channels = db.get_all_temp_channels()
        cleaned = 0

        for channel_data in channels:
            channel = self.bot.get_channel(channel_data["channel_id"])
            if not channel:
                db.delete_temp_channel(channel_data["channel_id"])
                cleaned += 1

        if cleaned > 0:
            log.tree("Orphan Cleanup", [
                ("Channels Removed", str(cleaned)),
                ("Reason", "Channel no longer exists"),
            ], emoji="🧹")

    def _build_panel_embed(
        self,
        channel: discord.VoiceChannel,
        owner: discord.Member,
        is_locked: bool = True
    ) -> discord.Embed:
        """Build the control panel embed."""
        channel_info = db.get_temp_channel(channel.id)
        owner_id = channel_info["owner_id"] if channel_info else owner.id

        # Get lists from owner's PERSISTENT lists (not channel-specific)
        trusted_list = db.get_trusted_list(owner_id)
        blocked_list = db.get_blocked_list(owner_id)

        # Validate trusted users still exist in guild, clean up stale entries
        valid_trusted = []
        for user_id in trusted_list:
            member = channel.guild.get_member(user_id)
            if member:
                valid_trusted.append((user_id, member))

        # Validate blocked users still exist
        valid_blocked_count = sum(1 for uid in blocked_list if channel.guild.get_member(uid))

        member_count = len(channel.members)
        limit = channel.user_limit or "∞"
        bitrate = channel.bitrate // 1000  # Convert to kbps

        # Get created_at timestamp for duration (stored as Unix timestamp)
        created_at = channel_info.get("created_at") if channel_info else None
        if created_at:
            try:
                # created_at is now stored as Unix timestamp (int)
                unix_ts = int(created_at)
                duration_text = f"<t:{unix_ts}:R>"  # Relative time (e.g., "2 minutes ago")
            except (ValueError, TypeError):
                duration_text = "Unknown"
        else:
            duration_text = "Just now"

        # Lock status
        if is_locked:
            status = "<:lock:1455709111684694107> Locked"
            color = 0xf04747  # Red
        else:
            status = "<:unlock:1455709112309514290> Unlocked"
            color = 0x43b581  # Green

        embed = discord.Embed(
            title=channel.name,
            color=color,
        )

        # Row 1: Owner, Status, Members
        embed.add_field(name="Owner", value=owner.mention, inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Members", value=f"{member_count}/{limit}", inline=True)

        # Row 2: Created, Bitrate, Allowed
        embed.add_field(name="Created", value=duration_text, inline=True)
        embed.add_field(name="Bitrate", value=f"{bitrate} kbps", inline=True)
        embed.add_field(name="Allowed", value=str(len(valid_trusted)), inline=True)

        # Current members in channel (always show)
        if channel.members:
            member_mentions = [m.mention for m in channel.members[:10]]
            members_text = " ".join(member_mentions)
            if len(channel.members) > 10:
                members_text += f" +{len(channel.members) - 10} more"
        else:
            members_text = "*No one yet*"
        embed.add_field(name="In Channel", value=members_text, inline=False)

        # Always show Allowed Users field (from owner's persistent list)
        if valid_trusted:
            # Show up to 8 users
            allowed_mentions = [member.mention for _, member in valid_trusted[:8]]
            allowed_text = " ".join(allowed_mentions)
            if len(valid_trusted) > 8:
                allowed_text += f" +{len(valid_trusted) - 8} more"
            embed.add_field(name="Allowed Users", value=allowed_text, inline=False)
        else:
            embed.add_field(name="Allowed Users", value="*None - use Allow button to add*", inline=False)

        embed.set_thumbnail(url=owner.display_avatar.url)
        set_footer(embed)

        return embed

    def _build_panel_view(self, is_locked: bool = True) -> ui.View:
        """Build control panel view with correct button states."""
        view = ui.View(timeout=None)

        # Row 1
        lock_emoji = "<:lock:1455709111684694107>" if is_locked else "<:unlock:1455709112309514290>"
        lock_label = "Locked" if is_locked else "Unlocked"

        view.add_item(ui.Button(label=lock_label, emoji=lock_emoji, style=discord.ButtonStyle.secondary, custom_id="tv_lock", row=0))
        view.add_item(ui.Button(label="Limit", emoji="<:limit:1455709299732123762>", style=discord.ButtonStyle.secondary, custom_id="tv_limit", row=0))
        view.add_item(ui.Button(label="Rename", emoji="<:rename:1455709387711578394>", style=discord.ButtonStyle.secondary, custom_id="tv_rename", row=0))

        # Row 2
        view.add_item(ui.Button(label="Allow", emoji="<:allow:1455709499792031744>", style=discord.ButtonStyle.secondary, custom_id="tv_permit", row=1))
        view.add_item(ui.Button(label="Block", emoji="<:block:1455709662316986539>", style=discord.ButtonStyle.secondary, custom_id="tv_block", row=1))
        view.add_item(ui.Button(label="Kick", emoji="<:kick:1455709879976198361>", style=discord.ButtonStyle.secondary, custom_id="tv_kick", row=1))

        # Row 3
        view.add_item(ui.Button(label="Claim", emoji="<:claim:1455709985467011173>", style=discord.ButtonStyle.secondary, custom_id="tv_claim", row=2))
        view.add_item(ui.Button(label="Transfer", emoji="<:transfer:1455710226429902858>", style=discord.ButtonStyle.secondary, custom_id="tv_transfer", row=2))
        view.add_item(ui.Button(label="Delete", emoji="<:delete:1455710362539397192>", style=discord.ButtonStyle.secondary, custom_id="tv_delete", row=2))

        return view

    def _update_lock_button(self, is_locked: bool) -> None:
        """Update the lock button appearance on the control panel."""
        for item in self.control_panel.children:
            if item.custom_id == "tv_lock":
                item.style = discord.ButtonStyle.secondary
                item.emoji = "<:lock:1455709111684694107>" if is_locked else "<:unlock:1455709112309514290>"
                item.label = "Locked" if is_locked else "Unlocked"
                break

    async def _send_channel_interface(
        self,
        channel: discord.VoiceChannel,
        owner: discord.Member,
        applied_allowed: int = 0,
        applied_blocked: int = 0
    ) -> discord.Message:
        """Send control panel to voice channel."""
        embed = self._build_panel_embed(channel, owner, is_locked=True)

        # Add applied counts as description if any were applied
        if applied_allowed > 0 or applied_blocked > 0:
            parts = []
            if applied_allowed > 0:
                parts.append(f"✅ {applied_allowed} allowed user{'s' if applied_allowed != 1 else ''} applied")
            if applied_blocked > 0:
                parts.append(f"🚫 {applied_blocked} blocked user{'s' if applied_blocked != 1 else ''} applied")
            embed.description = "\n".join(parts)

        # Update lock button to locked state
        self._update_lock_button(is_locked=True)
        # Use the registered control panel view (has callbacks)
        return await channel.send(embed=embed, view=self.control_panel)

    async def _update_panel(self, channel: discord.VoiceChannel) -> None:
        """Update the control panel embed in the channel, or recreate if missing."""
        channel_info = db.get_temp_channel(channel.id)
        if not channel_info:
            return

        owner = channel.guild.get_member(channel_info["owner_id"])
        if not owner:
            return

        is_locked = bool(channel_info.get("is_locked", 0))

        # Find the panel message (bot's message with embed)
        panel_found = False
        async for message in channel.history(limit=15):
            if message.author.id == self.bot.user.id and message.embeds:
                embed = self._build_panel_embed(channel, owner, is_locked)
                # Update lock button to match current state
                self._update_lock_button(is_locked)
                # Use the registered control panel view (has callbacks)
                await message.edit(embed=embed, view=self.control_panel)
                panel_found = True
                break

        # Panel was deleted - recreate it
        if not panel_found:
            embed = self._build_panel_embed(channel, owner, is_locked)
            self._update_lock_button(is_locked)
            await channel.send(embed=embed, view=self.control_panel)
            log.tree("Panel Recovered", [
                ("Channel", channel.name),
                ("Owner", str(owner)),
            ], emoji="🔧")

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ) -> None:
        """Handle voice state updates."""
        # Safety check - ensure member and guild are valid
        if not member or not member.guild:
            return

        # User left a VC - revoke text permissions
        if before.channel and before.channel.id != config.VC_CREATOR_CHANNEL_ID:
            # Re-fetch channel to ensure it still exists
            channel = member.guild.get_channel(before.channel.id)
            if channel:
                await self._revoke_text_access(channel, member)
                # Only check empty for temp channels
                if db.is_temp_channel(channel.id):
                    await self._check_empty_channel(channel)

        # User joined a VC - grant text permissions (works for dragged-in users too)
        if after.channel and after.channel.id != config.VC_CREATOR_CHANNEL_ID:
            # Re-fetch channel to ensure it still exists
            channel = member.guild.get_channel(after.channel.id)
            if channel:
                await self._grant_text_access(channel, member)

        # User joined the creator channel - create new temp VC
        if after.channel and after.channel.id == config.VC_CREATOR_CHANNEL_ID:
            await self._create_temp_channel(member)

    async def _grant_text_access(self, channel: discord.VoiceChannel, member: discord.Member) -> None:
        """Grant text chat access to a member in a temp VC (includes dragged-in users)."""
        try:
            # Get current overwrites to preserve other permissions
            overwrites = channel.overwrites_for(member)
            # Text access
            overwrites.view_channel = True
            overwrites.send_messages = True
            overwrites.read_message_history = True
            # Allow reconnecting if they leave (for dragged-in users)
            overwrites.connect = True
            await channel.set_permissions(member, overwrite=overwrites)
            # Update panel to show new member
            await self._update_panel(channel)
        except discord.HTTPException:
            pass  # Silently fail - not critical
        except Exception:
            pass

    async def _revoke_text_access(self, channel: discord.VoiceChannel, member: discord.Member) -> None:
        """Revoke text chat access from a member who left a VC."""
        try:
            channel_info = db.get_temp_channel(channel.id)

            # For temp channels - special handling
            if channel_info:
                # Don't revoke from owner - they always have access
                if member.id == channel_info["owner_id"]:
                    # Still update panel to reflect member left
                    await self._update_panel(channel)
                    return

                # Check if user is trusted - preserve their connect permission
                is_trusted = member.id in db.get_trusted_list(channel_info["owner_id"])

                if is_trusted:
                    # Keep connect=True but remove text access
                    overwrites = channel.overwrites_for(member)
                    overwrites.send_messages = False
                    overwrites.read_message_history = False
                    overwrites.connect = True
                    await channel.set_permissions(member, overwrite=overwrites)
                else:
                    # Not trusted - remove all custom permissions
                    await channel.set_permissions(member, overwrite=None)

                # Update panel to show member left
                await self._update_panel(channel)
            else:
                # For non-temp channels - just remove the text permissions we granted
                await channel.set_permissions(member, overwrite=None)
        except discord.HTTPException:
            pass  # Silently fail - not critical
        except Exception:
            pass

    async def _create_temp_channel(self, member: discord.Member) -> None:
        """Create a new temp voice channel for a member."""
        guild = member.guild

        # Check cooldown to prevent spam
        now = time.time()
        last_join = self._join_cooldowns.get(member.id, 0)
        if now - last_join < JOIN_COOLDOWN:
            remaining = JOIN_COOLDOWN - (now - last_join)
            log.tree("Join Cooldown", [
                ("User", str(member)),
                ("Remaining", f"{remaining:.1f}s"),
            ], emoji="⏳")
            # Disconnect them from creator channel
            try:
                await member.move_to(None)
            except discord.HTTPException:
                pass
            return

        # Update cooldown timestamp
        self._join_cooldowns[member.id] = now

        # Cleanup old cooldown entries (older than 1 minute) to prevent memory leak
        cutoff = now - 60
        self._join_cooldowns = {
            uid: ts for uid, ts in self._join_cooldowns.items()
            if ts > cutoff
        }

        # Check if user already owns a channel
        existing = db.get_owner_channel(member.id, guild.id)
        if existing:
            channel = guild.get_channel(existing)
            if channel:
                # Transfer ownership to someone else in the channel, or delete if empty
                other_members = [m for m in channel.members if m.id != member.id and not m.bot]
                if other_members:
                    # Transfer to first other member
                    new_owner = other_members[0]
                    try:
                        await channel.set_permissions(member, overwrite=None)
                        await channel.set_permissions(new_owner, connect=True, manage_channels=True, move_members=True, send_messages=True, read_message_history=True)
                        db.transfer_ownership(channel.id, new_owner.id)
                        log.tree("Auto-Transfer", [
                            ("Channel", channel.name),
                            ("From", str(member)),
                            ("To", str(new_owner)),
                        ], emoji="🔄")
                    except discord.HTTPException as e:
                        log.tree("Auto-Transfer Failed", [
                            ("Channel", channel.name),
                            ("From", str(member)),
                            ("To", str(new_owner)),
                            ("Error", str(e)),
                        ], emoji="❌")
                else:
                    # Channel is empty, delete it
                    try:
                        db.delete_temp_channel(channel.id)
                        await channel.delete(reason="Owner left, no other members")
                        log.tree("Channel Auto-Deleted", [
                            ("Channel", channel.name),
                            ("Reason", "Owner creating new VC"),
                        ], emoji="🗑️")
                    except discord.HTTPException as e:
                        log.tree("Auto-Delete Failed", [
                            ("Channel", channel.name),
                            ("Owner", str(member)),
                            ("Error", str(e)),
                        ], emoji="❌")
            else:
                db.delete_temp_channel(existing)

        # Clean up stale trusted/blocked users (who left the server)
        guild_member_ids = {m.id for m in guild.members}
        stale_removed = db.cleanup_stale_users(member.id, guild_member_ids)
        if stale_removed > 0:
            log.tree("Stale User Cleanup", [
                ("Owner", str(member)),
                ("Entries Removed", str(stale_removed)),
                ("Reason", "Users left server"),
            ], emoji="🧹")

        # Get user settings
        settings = db.get_user_settings(member.id)
        default_name = settings.get("default_name") if settings else None
        default_limit = settings.get("default_limit", 0) if settings else 0

        # Generate channel name
        if default_name:
            channel_name = default_name
            name_source = "saved"
        else:
            existing_channels = db.get_all_temp_channels(guild.id)
            channel_num = len(existing_channels) + 1
            roman = to_roman(channel_num)
            # Truncate display name if too long (Discord limit is 100 chars)
            display_name = member.display_name[:80]
            channel_name = f"{roman}・{display_name}"
            name_source = "generated"

        log.tree("Creating Channel", [
            ("Owner", str(member)),
            ("Name", channel_name),
            ("Source", name_source),
        ], emoji="🔧")

        # Get category
        category = None
        if config.VC_CATEGORY_ID:
            category = guild.get_channel(config.VC_CATEGORY_ID)

        try:
            # Build all overwrites upfront (single API call instead of multiple)
            overwrites = {
                # Lock by default + deny text access for everyone
                guild.default_role: discord.PermissionOverwrite(
                    connect=False,
                    send_messages=False,
                    read_message_history=False,
                ),
                # Owner permissions (full access including text)
                member: discord.PermissionOverwrite(
                    connect=True,
                    manage_channels=True,
                    move_members=True,
                    send_messages=True,
                    read_message_history=True,
                ),
            }

            # Mod role gets full access (except developer's channels)
            if config.MOD_ROLE_ID and member.id != config.OWNER_ID:
                mod_role = guild.get_role(config.MOD_ROLE_ID)
                if mod_role:
                    overwrites[mod_role] = discord.PermissionOverwrite(
                        connect=True,
                        speak=True,
                        mute_members=True,
                        deafen_members=True,
                        move_members=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_messages=True,
                        attach_files=True,
                        embed_links=True,
                    )

            # Pre-build blocked user overwrites
            blocked_count = 0
            for blocked_id in db.get_blocked_list(member.id):
                blocked_user = guild.get_member(blocked_id)
                if blocked_user:
                    is_mod = any(r.id == config.MOD_ROLE_ID for r in blocked_user.roles)
                    if is_mod and member.id != config.OWNER_ID:
                        continue
                    overwrites[blocked_user] = discord.PermissionOverwrite(connect=False)
                    blocked_count += 1

            # Pre-build trusted user overwrites
            trusted_count = 0
            for trusted_id in db.get_trusted_list(member.id):
                trusted_user = guild.get_member(trusted_id)
                if trusted_user:
                    overwrites[trusted_user] = discord.PermissionOverwrite(connect=True)
                    trusted_count += 1

            # Create channel with ALL permissions in one API call
            channel = await guild.create_voice_channel(
                name=channel_name,
                category=category,
                user_limit=default_limit,
                overwrites=overwrites,
                reason=f"TempVoice for {member}"
            )

            # Store in database (locked by default)
            db.create_temp_channel(channel.id, member.id, guild.id, channel_name)
            db.update_temp_channel(channel.id, is_locked=1)

            # Move user
            try:
                await member.move_to(channel)
            except discord.HTTPException as e:
                log.tree("Move User Failed", [
                    ("Channel", channel_name),
                    ("User", str(member)),
                    ("Error", str(e)),
                ], emoji="❌")
                # Channel was created but move failed - clean up
                db.delete_temp_channel(channel.id)
                await channel.delete(reason="Failed to move user")
                return

            # Send control panel with applied counts
            try:
                await self._send_channel_interface(channel, member, trusted_count, blocked_count)
            except Exception as e:
                log.tree("Panel Send Failed", [
                    ("Channel", channel_name),
                    ("Error", str(e)),
                ], emoji="⚠️")

            log.tree("Channel Created", [
                ("Channel", channel_name),
                ("Owner", str(member)),
                ("Allowed Applied", str(trusted_count)),
                ("Blocked Applied", str(blocked_count)),
            ], emoji="🔊")

        except discord.HTTPException as e:
            log.tree("Channel Creation Failed", [
                ("Owner", str(member)),
                ("Error", str(e)),
            ], emoji="❌")

    async def _check_empty_channel(self, channel: discord.VoiceChannel) -> None:
        """Check if channel is empty and should be deleted."""
        if not db.is_temp_channel(channel.id):
            return

        if len(channel.members) == 0:
            channel_name = channel.name
            channel_info = db.get_temp_channel(channel.id)
            owner_id = channel_info["owner_id"] if channel_info else "Unknown"

            db.delete_temp_channel(channel.id)
            try:
                await channel.delete(reason="Empty")
                log.tree("Channel Auto-Deleted", [
                    ("Channel", channel_name),
                    ("Owner ID", str(owner_id)),
                ], emoji="🗑️")
            except discord.HTTPException:
                pass
