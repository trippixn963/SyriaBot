"""
SyriaBot - TempVoice User Selects
=================================

User select dropdowns for TempVoice control panel.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import TYPE_CHECKING

import discord
from discord import ui

from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING, COLOR_NEUTRAL, COLOR_BOOST
from src.core.config import config
from src.core.constants import SELECT_TIMEOUT_DEFAULT
from src.core.logger import logger
from src.services.database import db
from .utils import (
    is_booster,
    has_vc_mod_role,
    MAX_ALLOWED_USERS_FREE,
    set_owner_permissions,
    get_trusted_overwrite,
    get_blocked_overwrite,
)

if TYPE_CHECKING:
    from .service import TempVoiceService


class UserSelectView(ui.View):
    """View for user selection actions."""

    def __init__(self, channel: discord.VoiceChannel, action: str, service: "TempVoiceService" = None) -> None:
        super().__init__(timeout=SELECT_TIMEOUT_DEFAULT)
        self.channel = channel
        self.action = action
        self.service = service
        self.message: discord.Message = None
        self.add_item(UserSelect(channel, action, service))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item) -> None:
        """Handle unexpected errors in user select view callbacks."""
        logger.error_tree("User Select View Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("User ID", str(interaction.user.id)),
            ("Action", self.action),
        ])
        try:
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        """Handle timeout - disable dropdown and update message."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                embed = discord.Embed(description="⏳ Selection expired", color=COLOR_NEUTRAL)
                await self.message.edit(embed=embed, view=None)
            except discord.NotFound:
                pass  # Message already deleted
            except discord.HTTPException as e:
                logger.error_tree("User Select Timeout Edit Failed", e, [
                    ("Action", self.action),
                ])
        logger.tree("User Select Expired", [
            ("Action", self.action),
            ("Channel", self.channel.name if self.channel else "Unknown"),
        ], emoji="⏳")


class UserSelect(ui.UserSelect):
    """User select dropdown."""

    def __init__(self, channel: discord.VoiceChannel, action: str, service: "TempVoiceService" = None) -> None:
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

    async def callback(self, interaction: discord.Interaction) -> None:
        user = self.values[0]

        try:
            # Validate channel still exists
            channel = interaction.guild.get_channel(self.channel.id)
            if not channel:
                embed = discord.Embed(description="❌ Channel no longer exists", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.tree("User Select Failed", [
                    ("Action", self.action),
                    ("Channel ID", str(self.channel.id)),
                    ("Reason", "Channel deleted"),
                ], emoji="❌")
                return

            channel_info = db.get_temp_channel(channel.id)
            if not channel_info:
                embed = discord.Embed(description="❌ Channel not found", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.tree("User Select Failed", [
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
            logger.error_tree("User Select Failed", e, [
                ("Action", self.action),
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to complete action", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error_tree("User Select Error", e, [
                ("Action", self.action),
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _handle_permit(self, interaction: discord.Interaction, channel: discord.VoiceChannel, user: discord.Member, owner_id: int) -> None:
        """Handle permit/unpermit action."""
        if user.id == owner_id:
            embed = discord.Embed(description="⚠️ Can't permit yourself", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("Permit Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Reason", "Self-permit"),
            ], emoji="⚠️")
            return
        if user.bot:
            embed = discord.Embed(description="⚠️ Can't permit bots", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("Permit Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
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
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.tree("Permit Blocked", [
                    ("Channel", channel.name),
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                    ("Reason", f"Max {MAX_ALLOWED_USERS_FREE} reached"),
                ], emoji="💎")
                return

        # Remove from blocked if was blocked
        db.remove_blocked(owner_id, user.id)
        if db.add_trusted(owner_id, user.id):
            # Grant connect + permanent text access (even when not in VC)
            await channel.set_permissions(user, overwrite=get_trusted_overwrite())
            total_allowed = len(db.get_trusted_list(owner_id))
            embed = discord.Embed(
                description=f"✅ **{user.display_name}** added to allowed list\n`{total_allowed}` users allowed • Can access chat anytime",
                color=COLOR_SUCCESS
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("User Permitted", [
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
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("User Unpermitted", [
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
                logger.error_tree("Panel Update Failed", e, [
                    ("Channel", channel.name),
                    ("Context", "After permit"),
                ])

    async def _handle_block(self, interaction: discord.Interaction, channel: discord.VoiceChannel, user: discord.Member, owner_id: int) -> None:
        """Handle block/unblock action."""
        if user.id == owner_id:
            embed = discord.Embed(description="⚠️ Can't block yourself", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("Block Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Reason", "Self-block"),
            ], emoji="⚠️")
            return
        if user.bot:
            embed = discord.Embed(description="⚠️ Can't block bots", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("Block Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Reason", "Is bot"),
            ], emoji="⚠️")
            return

        # Check if target has VC mod role - can only be blocked by developer
        if has_vc_mod_role(user) and owner_id != config.OWNER_ID:
            embed = discord.Embed(description="⚠️ Can't block moderators", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("Block Rejected", [
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
            # Set permission to deny connect
            await channel.set_permissions(user, overwrite=get_blocked_overwrite())

            # Kick from channel if currently in it
            was_kicked = False
            if user.voice and user.voice.channel == channel:
                try:
                    await user.move_to(None)
                    was_kicked = True
                except discord.HTTPException as e:
                    logger.error_tree("Blocked User Kick Failed", e, [
                        ("Channel", channel.name),
                        ("User", f"{user.name} ({user.display_name})"),
                        ("ID", str(user.id)),
                    ])

            total_blocked = len(db.get_blocked_list(owner_id))
            if was_kicked:
                embed = discord.Embed(
                    description=f"🚫 **{user.display_name}** blocked and kicked\n`{total_blocked}` users blocked",
                    color=COLOR_ERROR
                )
            else:
                embed = discord.Embed(
                    description=f"🚫 **{user.display_name}** added to blocked list\n`{total_blocked}` users blocked",
                    color=COLOR_ERROR
                )
            embed.set_thumbnail(url=user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("User Blocked", [
                ("Channel", channel.name),
                ("Target", f"{user.name} ({user.display_name})"),
                ("Target ID", str(user.id)),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("By ID", str(interaction.user.id)),
                ("Kicked", "Yes" if was_kicked else "No"),
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
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("User Unblocked", [
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
                logger.error_tree("Panel Update Failed", e, [
                    ("Channel", channel.name),
                    ("Context", "After block"),
                ])

    async def _handle_kick(self, interaction: discord.Interaction, channel: discord.VoiceChannel, user: discord.Member, owner_id: int) -> None:
        """Handle kick action."""
        if user.id == owner_id:
            embed = discord.Embed(description="⚠️ Can't kick yourself", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("Kick Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Reason", "Self-kick"),
            ], emoji="⚠️")
            return

        # Protect VC mod roles from being kicked (developer can kick anyone)
        if has_vc_mod_role(user) and owner_id != config.OWNER_ID:
            embed = discord.Embed(description="⚠️ Can't kick staff members", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("Kick Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Reason", "Has VC mod role"),
            ], emoji="⚠️")
            return

        if user.voice and user.voice.channel == channel:
            await user.move_to(None)
            embed = discord.Embed(
                description=f"👢 **{user.display_name}** kicked from channel",
                color=COLOR_ERROR
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("User Kicked", [
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
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("Kick Rejected", [
                ("Channel", channel.name),
                ("Target", f"{user.name} ({user.display_name})"),
                ("Target ID", str(user.id)),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("By ID", str(interaction.user.id)),
                ("Reason", "Not in channel"),
            ], emoji="⚠️")

    async def _handle_transfer(self, interaction: discord.Interaction, channel: discord.VoiceChannel, user: discord.Member, owner_id: int) -> None:
        """Handle transfer action."""
        if user.id == owner_id:
            embed = discord.Embed(description="⚠️ Already the owner", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("Transfer Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Reason", "Already owner"),
            ], emoji="⚠️")
            return
        if user.bot:
            embed = discord.Embed(description="⚠️ Can't transfer to bots", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree("Transfer Rejected", [
                ("Channel", channel.name),
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Reason", "Is bot"),
            ], emoji="⚠️")
            return

        # Check if target is in the voice channel
        if not user.voice or user.voice.channel != channel:
            embed = discord.Embed(
                description=f"⚠️ **{user.display_name}** is not in the channel",
                color=COLOR_WARNING,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Check if target already owns a channel
        existing = db.get_owner_channel(user.id, interaction.guild.id)
        if existing:
            existing_channel = interaction.guild.get_channel(existing)
            if existing_channel:
                embed = discord.Embed(
                    description=f"❌ **{user.display_name}** already owns another channel",
                    color=COLOR_ERROR,
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            else:
                db.delete_temp_channel(existing)

        # Defer — the following API calls can be slow
        await interaction.response.defer(ephemeral=True)

        # Execute transfer directly
        channel_info = db.get_temp_channel(channel.id)
        if not channel_info or channel_info["owner_id"] != interaction.user.id:
            embed = discord.Embed(description="❌ You no longer own this channel", color=COLOR_ERROR)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        channel_name = await self.service._transfer_ownership(channel, interaction.user.id, user)

        embed = discord.Embed(
            description=f"🔄 Transferred to **{user.display_name}**\nChannel renamed to `{channel_name}`",
            color=COLOR_SUCCESS,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

        logger.tree("Channel Transferred", [
            ("Channel", channel_name),
            ("From", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("From ID", str(interaction.user.id)),
            ("To", f"{user.name} ({user.display_name})"),
            ("To ID", str(user.id)),
        ], emoji="🔄")

        # Update panel to reflect new owner
        if self.service:
            try:
                await self.service._update_panel(channel)
            except Exception as e:
                logger.error_tree("Panel Update Failed", e, [
                    ("Channel", channel.name),
                    ("Context", "After transfer"),
                ])
