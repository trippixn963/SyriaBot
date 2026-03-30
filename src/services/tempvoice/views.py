"""
SyriaBot - TempVoice Control Panel
==================================

Control panel views for TempVoice channels.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import TYPE_CHECKING, Optional

import discord
from discord import ui

from src.core.colors import (
    COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING, COLOR_NEUTRAL, COLOR_BOOST,
    EMOJI_LOCK, EMOJI_UNLOCK, EMOJI_LIMIT, EMOJI_RENAME, EMOJI_ALLOW,
    EMOJI_BLOCK, EMOJI_KICK, EMOJI_CLAIM, EMOJI_TRANSFER, EMOJI_DELETE,
)
from src.core.config import config
from src.core.constants import CLAIM_APPROVAL_TIMEOUT
from src.core.logger import logger
from src.services.database import db
from .modals import NameModal, LimitModal
from .selects import UserSelectView
from .utils import is_booster, has_vc_mod_role, set_owner_permissions, get_locked_overwrite, get_unlocked_overwrite

if TYPE_CHECKING:
    from .service import TempVoiceService


class ClaimApprovalView(ui.View):
    """View for owner to approve/deny claim requests."""

    def __init__(self, channel: discord.VoiceChannel, requester: discord.Member, owner: discord.Member, service: "TempVoiceService") -> None:
        super().__init__(timeout=CLAIM_APPROVAL_TIMEOUT)
        self.channel = channel
        self.requester = requester
        self.owner = owner
        self.service = service
        self.message: Optional[discord.Message] = None

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item) -> None:
        """Handle unexpected errors in claim approval callbacks."""
        custom_id = getattr(item, "custom_id", "unknown")
        logger.error_tree("Claim Approval Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("User ID", str(interaction.user.id)),
            ("Button", custom_id),
        ])
        try:
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.HTTPException as e:
            logger.debug("Claim Error Reply Failed", [("Error", str(e)[:50])])

    async def on_timeout(self) -> None:
        """Handle timeout - deny by default."""
        # Remove from pending claims
        if self.service:
            self.service._pending_claims.discard(self.channel.id)

        try:
            if self.message:
                embed = self.message.embeds[0]
                embed.color = COLOR_NEUTRAL
                await self.message.edit(embed=embed, view=None)
                logger.tree("Claim Request Expired", [
                    ("Channel", self.channel.name),
                    ("Requester", f"{self.requester.name} ({self.requester.display_name})"),
                    ("Requester ID", str(self.requester.id)),
                    ("Owner", f"{self.owner.name} ({self.owner.display_name})"),
                    ("Owner ID", str(self.owner.id)),
                ], emoji="⏳")
        except discord.HTTPException as e:
            logger.error_tree("Claim Timeout Update Failed", e, [
                ("Channel", self.channel.name),
            ])
        except Exception as e:
            logger.error_tree("Claim Timeout Error", e, [
                ("Channel", self.channel.name),
            ])

    @ui.button(label="Approve", style=discord.ButtonStyle.secondary, emoji=EMOJI_ALLOW)
    async def approve(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            # Only owner can approve — don't clear pending flag for non-owner clicks
            if interaction.user.id != self.owner.id:
                embed = discord.Embed(description="⚠️ Only the owner can respond to this request", color=COLOR_WARNING)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.tree("Claim Approve Rejected", [
                    ("Channel", self.channel.name),
                    ("Attempted By", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                    ("Reason", "Not owner"),
                ], emoji="⚠️")
                return

            # Owner confirmed — clear pending flag
            if self.service:
                self.service._pending_claims.discard(self.channel.id)

            # Validate channel still exists
            channel = interaction.guild.get_channel(self.channel.id)
            if not channel:
                embed = discord.Embed(description="❌ Channel no longer exists", color=COLOR_ERROR)
                await interaction.response.edit_message(embed=embed, view=None)
                logger.tree("Claim Approve Failed", [
                    ("Channel ID", str(self.channel.id)),
                    ("Reason", "Channel deleted"),
                ], emoji="❌")
                return

            # Validate requester is still in the channel
            requester = interaction.guild.get_member(self.requester.id)
            if not requester or requester.voice is None or requester.voice.channel != channel:
                embed = discord.Embed(
                    description=f"❌ **{self.requester.display_name}** is no longer in the channel",
                    color=COLOR_ERROR
                )
                await interaction.response.edit_message(embed=embed, view=None)
                logger.tree("Claim Approve Failed", [
                    ("Channel", channel.name),
                    ("Requester", f"{self.requester.name} ({self.requester.display_name})"),
                    ("Requester ID", str(self.requester.id)),
                    ("Reason", "Requester left channel"),
                ], emoji="❌")
                return

            # Check if requester already owns a channel
            existing = db.get_owner_channel(requester.id, interaction.guild.id)
            if existing:
                # Verify the channel still exists in Discord (clean up stale DB entries)
                existing_channel = interaction.guild.get_channel(existing)
                if existing_channel:
                    embed = discord.Embed(
                        description=f"❌ **{requester.display_name}** already owns another channel",
                        color=COLOR_ERROR
                    )
                    await interaction.response.edit_message(embed=embed, view=None)
                    logger.tree("Claim Approve Failed", [
                        ("Channel", channel.name),
                        ("Requester", f"{requester.name} ({requester.display_name})"),
                        ("Requester ID", str(requester.id)),
                        ("Reason", "Already owns channel"),
                    ], emoji="❌")
                    return
                else:
                    # Stale DB entry — channel was deleted, clean it up
                    db.delete_temp_channel(existing)
                    logger.tree("Orphan DB Entry Cleaned", [
                        ("Channel ID", str(existing)),
                        ("Owner", f"{requester.name} ({requester.display_name})"),
                    ], emoji="🧹")

            # Set new owner permissions
            try:
                await set_owner_permissions(channel, requester)
            except discord.Forbidden:
                embed = discord.Embed(
                    description="❌ Bot lacks permission to transfer ownership",
                    color=COLOR_ERROR
                )
                await interaction.response.edit_message(embed=embed, view=None)
                logger.tree("Claim Approve Failed", [
                    ("Channel", channel.name),
                    ("Reason", "Missing permissions"),
                ], emoji="❌")
                self.stop()
                return

            # Cancel any pending auto-transfer for this channel
            if self.service:
                task = self.service._pending_transfers.pop(channel.id, None)
                if task:
                    task.cancel()

            # Update DB ownership
            db.transfer_ownership(channel.id, requester.id)

            # Respond IMMEDIATELY (heavy work happens after)
            embed = discord.Embed(
                description=f"✅ **{requester.display_name}** is now the owner",
                color=COLOR_SUCCESS
            )
            embed.set_thumbnail(url=requester.display_avatar.url)
            await interaction.response.edit_message(embed=embed, view=None)

            logger.tree("Claim Approved", [
                ("Channel", channel.name),
                ("New Owner", f"{requester.name} ({requester.display_name})"),
                ("New Owner ID", str(requester.id)),
                ("Approved By", f"{self.owner.name} ({self.owner.display_name})"),
                ("Approved By ID", str(self.owner.id)),
            ], emoji="👑")

            # Now do heavy work — _apply_owner_lists skips current VC members
            # during the wipe so nobody loses text access mid-transfer
            if self.service:
                try:
                    await self.service._rename_for_new_owner(channel, requester)
                    await self.service._apply_owner_lists(channel, requester)
                    await self.service._update_panel(channel)
                except Exception as e:
                    logger.error_tree("Post-Claim Setup Failed", e, [
                        ("Channel", channel.name),
                        ("New Owner", f"{requester.name}"),
                    ])

        except discord.HTTPException as e:
            logger.error_tree("Claim Approve Failed", e, [
                ("Channel", self.channel.name),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to process approval", color=COLOR_ERROR)
                await interaction.response.edit_message(embed=embed, view=None)
        except Exception as e:
            logger.error_tree("Claim Approve Error", e, [
                ("Channel", self.channel.name),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)

        self.stop()

    @ui.button(label="Deny", style=discord.ButtonStyle.secondary, emoji=EMOJI_BLOCK)
    async def deny(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            # Only owner can deny — don't clear pending flag for non-owner clicks
            if interaction.user.id != self.owner.id:
                embed = discord.Embed(description="⚠️ Only the owner can respond to this request", color=COLOR_WARNING)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.tree("Claim Deny Rejected", [
                    ("Channel", self.channel.name),
                    ("Attempted By", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                    ("Reason", "Not owner"),
                ], emoji="⚠️")
                return

            # Owner confirmed — clear pending flag
            if self.service:
                self.service._pending_claims.discard(self.channel.id)

            embed = discord.Embed(
                description=f"❌ Claim request from **{self.requester.display_name}** denied",
                color=COLOR_ERROR
            )
            await interaction.response.edit_message(embed=embed, view=None)

            logger.tree("Claim Denied", [
                ("Channel", self.channel.name),
                ("Requester", f"{self.requester.name} ({self.requester.display_name})"),
                ("Requester ID", str(self.requester.id)),
                ("Denied By", f"{self.owner.name} ({self.owner.display_name})"),
                ("Denied By ID", str(self.owner.id)),
            ], emoji="🚫")

        except discord.HTTPException as e:
            logger.error_tree("Claim Deny Failed", e, [
                ("Channel", self.channel.name),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to process denial", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error_tree("Claim Deny Error", e, [
                ("Channel", self.channel.name),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)

        self.stop()


class TempVoiceControlPanel(ui.View):
    """Control panel for temp voice channels."""

    def __init__(self, service: "TempVoiceService") -> None:
        super().__init__(timeout=None)
        self.service = service

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item) -> None:
        """Handle unexpected errors in control panel callbacks."""
        custom_id = getattr(item, "custom_id", "unknown")
        logger.error_tree("Control Panel Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("User ID", str(interaction.user.id)),
            ("Button", custom_id),
        ])
        try:
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.HTTPException as e:
            logger.debug("Control Panel Error Reply Failed", [("Error", str(e)[:50])])

    async def _get_user_channel(self, interaction: discord.Interaction, log_context: str = "Action") -> Optional[discord.VoiceChannel]:
        """Get the user's temp voice channel."""
        channel_id = db.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            embed = discord.Embed(description="⚠️ You don't own a channel", color=COLOR_WARNING)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree(f"{log_context} Rejected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "No owned channel"),
            ], emoji="⚠️")
            return None

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            db.delete_temp_channel(channel_id)
            embed = discord.Embed(description="❌ Channel no longer exists", color=COLOR_ERROR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.tree(f"{log_context} Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Channel ID", str(channel_id)),
                ("Reason", "Channel deleted"),
            ], emoji="❌")
            return None

        return channel

    # Row 1: Lock, Limit, Rename
    @ui.button(label="Locked", emoji=EMOJI_LOCK, style=discord.ButtonStyle.secondary, custom_id="tv_lock", row=0)
    async def lock_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Toggle lock/unlock."""
        try:
            channel = await self._get_user_channel(interaction, "Lock Toggle")
            if not channel:
                return

            channel_info = db.get_temp_channel(channel.id)
            if not channel_info:
                embed = discord.Embed(description="❌ Channel data not found", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            is_locked = channel_info.get("is_locked", 0)
            new_locked = 0 if is_locked else 1
            everyone = interaction.guild.default_role

            # Require level 10 to lock (unlocking always allowed)
            # Bypass: developer, VC mods, boosters
            can_bypass = (
                interaction.user.id == config.OWNER_ID
                or has_vc_mod_role(interaction.user)
                or (hasattr(interaction.user, 'premium_since') and interaction.user.premium_since)
            )
            if new_locked and not can_bypass:
                user_data = db.get_user_xp(interaction.user.id, interaction.guild.id)
                user_level = user_data["level"] if user_data else 0
                if user_level < 10:
                    embed = discord.Embed(
                        description=f"🔒 You need to be **Level 10** to lock your channel\nYou are currently **Level {user_level}**",
                        color=COLOR_WARNING,
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    logger.tree("Lock Denied — Level Too Low", [
                        ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                        ("ID", str(interaction.user.id)),
                        ("Level", str(user_level)),
                        ("Required", "10"),
                    ], emoji="🔒")
                    return

            # Defer first — set_permissions can be slow
            await interaction.response.defer(ephemeral=True)

            if new_locked:
                await channel.set_permissions(everyone, overwrite=get_locked_overwrite())
            else:
                await channel.set_permissions(everyone, overwrite=get_unlocked_overwrite())

            db.update_temp_channel(channel.id, is_locked=new_locked)

            # Respond with actual result after success
            if new_locked:
                embed = discord.Embed(
                    description=f"{EMOJI_LOCK} Channel is now **locked**",
                    color=COLOR_ERROR
                )
            else:
                embed = discord.Embed(
                    description=f"{EMOJI_UNLOCK} Channel is now **unlocked**",
                    color=COLOR_SUCCESS
                )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.tree("Lock Toggled", [
                ("Channel", channel.name),
                ("Status", "Locked" if new_locked else "Unlocked"),
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ], emoji="🔒" if new_locked else "🔓")

            # Update panel to reflect new state
            try:
                await self.service._update_panel(channel)
            except Exception as e:
                logger.error_tree("Panel Update Failed", e, [
                    ("Channel", channel.name),
                    ("Context", "After lock toggle"),
                ])

        except discord.HTTPException as e:
            logger.error_tree("Lock Toggle Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            embed = discord.Embed(description="❌ Failed to update channel", color=COLOR_ERROR)
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error_tree("Lock Toggle Error", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Limit", emoji=EMOJI_LIMIT, style=discord.ButtonStyle.secondary, custom_id="tv_limit", row=0)
    async def limit_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Set user limit."""
        try:
            channel = await self._get_user_channel(interaction, "Limit")
            if channel:
                await interaction.response.send_modal(LimitModal(channel))
        except discord.HTTPException as e:
            logger.error_tree("Limit Button Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to open limit modal", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error_tree("Limit Button Error", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Rename", emoji=EMOJI_RENAME, style=discord.ButtonStyle.secondary, custom_id="tv_rename", row=0)
    async def rename_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Rename channel - Booster only."""
        try:
            # Check if user is a booster
            if not is_booster(interaction.user):
                # Get their channel info for context
                channel_id = db.get_owner_channel(interaction.user.id, interaction.guild.id)
                channel = interaction.guild.get_channel(channel_id) if channel_id else None
                current_name = channel.name if channel else "No channel"

                embed = discord.Embed(
                    title="💎 Booster Feature",
                    description="Channel renaming is a **booster-only** feature!",
                    color=COLOR_BOOST
                )
                if channel:
                    embed.add_field(
                        name="🔊 Your Channel",
                        value=channel.mention,
                        inline=True
                    )
                    embed.add_field(
                        name="📝 Current Name",
                        value=f"`{current_name}`",
                        inline=True
                    )
                embed.add_field(
                    name="💎 Boost to Unlock",
                    value=(
                        "• Custom channel names\n"
                        "• Unlimited allowed users\n"
                        "• Support the community!"
                    ),
                    inline=False
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.tree("Rename Blocked", [
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                    ("Reason", "Not a booster"),
                ], emoji="💎")
                return

            channel = await self._get_user_channel(interaction, "Rename")
            if channel:
                await interaction.response.send_modal(NameModal(channel, interaction.user))
        except discord.HTTPException as e:
            logger.error_tree("Rename Button Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to open rename modal", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error_tree("Rename Button Error", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    # Row 2: Permit, Block, Kick
    @ui.button(label="Allow", emoji=EMOJI_ALLOW, style=discord.ButtonStyle.secondary, custom_id="tv_permit", row=1)
    async def permit_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Permit/unpermit a user."""
        try:
            channel = await self._get_user_channel(interaction, "Allow")
            if channel:
                embed = discord.Embed(description="👤 Select user to allow (select again to remove)", color=COLOR_NEUTRAL)
                view = UserSelectView(channel, "permit", self.service)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                view.message = await interaction.original_response()
        except discord.HTTPException as e:
            logger.error_tree("Allow Button Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to show user select", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error_tree("Allow Button Error", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Block", emoji=EMOJI_BLOCK, style=discord.ButtonStyle.secondary, custom_id="tv_block", row=1)
    async def block_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Block/unblock a user."""
        try:
            channel = await self._get_user_channel(interaction, "Block")
            if channel:
                embed = discord.Embed(description="🚫 Select user to block (select again to unblock)", color=COLOR_NEUTRAL)
                view = UserSelectView(channel, "block", self.service)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                view.message = await interaction.original_response()
        except discord.HTTPException as e:
            logger.error_tree("Block Button Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to show user select", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error_tree("Block Button Error", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Kick", emoji=EMOJI_KICK, style=discord.ButtonStyle.secondary, custom_id="tv_kick", row=1)
    async def kick_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Kick a user."""
        try:
            channel = await self._get_user_channel(interaction, "Kick")
            if channel:
                embed = discord.Embed(description="👢 Select user to kick from channel", color=COLOR_NEUTRAL)
                view = UserSelectView(channel, "kick")
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                view.message = await interaction.original_response()
        except discord.HTTPException as e:
            logger.error_tree("Kick Button Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to show user select", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error_tree("Kick Button Error", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    # Row 3: Claim, Transfer, Delete
    @ui.button(label="Claim", emoji=EMOJI_CLAIM, style=discord.ButtonStyle.secondary, custom_id="tv_claim", row=2)
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Request to claim channel - requires owner approval."""
        try:
            if not interaction.user.voice or not interaction.user.voice.channel:
                embed = discord.Embed(description="⚠️ Join a voice channel first", color=COLOR_WARNING)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.tree("Claim Rejected", [
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                    ("Reason", "Not in voice channel"),
                ], emoji="⚠️")
                return

            channel = interaction.user.voice.channel
            channel_info = db.get_temp_channel(channel.id)

            if not channel_info:
                embed = discord.Embed(description="⚠️ Not a temp channel", color=COLOR_WARNING)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.tree("Claim Rejected", [
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                    ("Channel", channel.name),
                    ("Reason", "Not a temp channel"),
                ], emoji="⚠️")
                return

            # Check if a claim is already pending for this channel
            if self.service and channel.id in self.service._pending_claims:
                embed = discord.Embed(description="⚠️ A claim is already pending for this channel", color=COLOR_WARNING)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.tree("Claim Rejected", [
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                    ("Channel", channel.name),
                    ("Reason", "Claim already pending"),
                ], emoji="⚠️")
                return

            owner_id = channel_info["owner_id"]
            owner = interaction.guild.get_member(owner_id)

            # Can't claim your own channel
            if interaction.user.id == owner_id:
                embed = discord.Embed(description="⚠️ You already own this channel", color=COLOR_WARNING)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.tree("Claim Rejected", [
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                    ("Channel", channel.name),
                    ("Reason", "Already owner"),
                ], emoji="⚠️")
                return

            existing = db.get_owner_channel(interaction.user.id, interaction.guild.id)
            if existing:
                existing_channel = interaction.guild.get_channel(existing)
                if existing_channel:
                    embed = discord.Embed(description="⚠️ You already own a channel", color=COLOR_WARNING)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    logger.tree("Claim Rejected", [
                        ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                        ("ID", str(interaction.user.id)),
                        ("Channel", channel.name),
                        ("Reason", "Owns another channel"),
                    ], emoji="⚠️")
                    return
                else:
                    db.delete_temp_channel(existing)
                    logger.tree("Orphan DB Entry Cleaned", [
                        ("Channel ID", str(existing)),
                        ("Owner", f"{interaction.user.name}"),
                    ], emoji="🧹")

            # If owner left the server, allow instant claim
            if not owner:
                if self.service:
                    self.service._pending_claims.add(channel.id)
                # Defer first — set_owner_permissions calls Discord API which can be slow
                await interaction.response.defer(ephemeral=True)
                try:
                    # Cancel any pending auto-transfer
                    if self.service:
                        task = self.service._pending_transfers.pop(channel.id, None)
                        if task:
                            task.cancel()

                    if self.service:
                        await self.service._transfer_ownership(channel, owner_id, interaction.user)
                    else:
                        await set_owner_permissions(channel, interaction.user)
                        db.transfer_ownership(channel.id, interaction.user.id)

                    embed = discord.Embed(
                        description=f"👑 You now own **{channel.name}**\nPrevious owner left the server",
                        color=COLOR_SUCCESS
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    logger.tree("Channel Claimed", [
                        ("Channel", channel.name),
                        ("New Owner", f"{interaction.user.name}"),
                        ("New Owner ID", str(interaction.user.id)),
                        ("Previous Owner", f"ID {owner_id} (left server)"),
                    ], emoji="👑")

                    if self.service:
                        try:
                            await self.service._update_panel(channel)
                        except Exception as e:
                            logger.error_tree("Panel Update Failed", e, [
                                ("Channel", channel.name),
                                ("Context", "After instant claim"),
                            ])
                finally:
                    if self.service:
                        self.service._pending_claims.discard(channel.id)
                return

            # Owner still exists - send approval request
            embed = discord.Embed(
                title="🔔 Claim Request",
                description=f"{interaction.user.mention} wants to claim this channel",
                color=COLOR_WARNING
            )
            embed.add_field(name="Requester", value=interaction.user.mention, inline=True)
            embed.add_field(name="Current Owner", value=owner.mention, inline=True)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)

            # Send approval request to channel, pinging owner
            if self.service:
                self.service._pending_claims.add(channel.id)
            try:
                view = ClaimApprovalView(channel, interaction.user, owner, self.service)
                msg = await channel.send(content=owner.mention, embed=embed, view=view)
                view.message = msg
            except Exception:
                # Clean up pending flag if sending the approval message fails
                if self.service:
                    self.service._pending_claims.discard(channel.id)
                raise

            response_embed = discord.Embed(
                description=f"📨 Claim request sent!\nWaiting for **{owner.display_name}** to approve...",
                color=COLOR_NEUTRAL
            )
            await interaction.response.send_message(embed=response_embed, ephemeral=True)

            logger.tree("Claim Requested", [
                ("Channel", channel.name),
                ("Requester", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("Requester ID", str(interaction.user.id)),
                ("Owner", f"{owner.name} ({owner.display_name})"),
                ("Owner ID", str(owner.id)),
            ], emoji="📨")

        except discord.HTTPException as e:
            logger.error_tree("Claim Button Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to process claim", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error_tree("Claim Button Error", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Transfer", emoji=EMOJI_TRANSFER, style=discord.ButtonStyle.secondary, custom_id="tv_transfer", row=2)
    async def transfer_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Transfer ownership."""
        try:
            channel = await self._get_user_channel(interaction, "Transfer")
            if channel:
                embed = discord.Embed(description="🔄 Select new owner to transfer channel", color=COLOR_NEUTRAL)
                view = UserSelectView(channel, "transfer", self.service)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                view.message = await interaction.original_response()
        except discord.HTTPException as e:
            logger.error_tree("Transfer Button Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to show user select", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error_tree("Transfer Button Error", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Clear", emoji=EMOJI_DELETE, style=discord.ButtonStyle.secondary, custom_id="tv_clear", row=2)
    async def clear_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Clear VC chat messages."""
        try:
            channel = await self._get_user_channel(interaction, "Clear")
            if not channel:
                return

            await interaction.response.defer(ephemeral=True)
            await channel.purge(limit=500, reason="Chat cleared by owner")

            if self.service:
                await self.service._resend_sticky_panel(channel)

            embed = discord.Embed(description="🧹 Chat cleared", color=COLOR_SUCCESS)
            await interaction.followup.send(embed=embed, ephemeral=True)

            logger.tree("Chat Cleared", [
                ("Channel", channel.name),
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ], emoji="🧹")

        except discord.HTTPException as e:
            logger.error_tree("Clear Button Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to clear chat", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(description="❌ Failed to clear chat", color=COLOR_ERROR)
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error_tree("Clear Button Error", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                await interaction.followup.send(embed=embed, ephemeral=True)
