"""
TempVoice - Control Panel Views
"""

from typing import TYPE_CHECKING, Optional

import discord
from discord import ui

from src.core.logger import log
from src.services.database import db
from src.services.webhook_logger import webhook_logger
from src.utils.footer import set_footer
from .modals import NameModal, LimitModal
from .selects import UserSelectView, ConfirmView
from .utils import is_booster, COLOR_BOOST

if TYPE_CHECKING:
    from .service import TempVoiceService


# Consistent colors
COLOR_SUCCESS = 0x43b581  # Green
COLOR_ERROR = 0xf04747    # Red
COLOR_WARNING = 0xfaa61a  # Orange
COLOR_NEUTRAL = 0x95a5a6  # Gray


class ClaimApprovalView(ui.View):
    """View for owner to approve/deny claim requests."""

    def __init__(self, channel: discord.VoiceChannel, requester: discord.Member, owner: discord.Member, service: "TempVoiceService"):
        super().__init__(timeout=300)  # 5 minute timeout
        self.channel = channel
        self.requester = requester
        self.owner = owner
        self.service = service

    async def on_timeout(self):
        """Handle timeout - deny by default."""
        try:
            # Find and update the message
            async for message in self.channel.history(limit=20):
                if message.author.id == self.channel.guild.me.id and message.embeds:
                    embed = message.embeds[0]
                    if embed.title and "Claim Request" in embed.title:
                        embed.color = 0x95a5a6  # Gray
                        embed.set_footer(text="Request expired")
                        await message.edit(embed=embed, view=None)
                        log.tree("Claim Request Expired", [
                            ("Channel", self.channel.name),
                            ("Requester", str(self.requester)),
                            ("Owner", str(self.owner)),
                        ], emoji="⏳")
                        break
        except discord.HTTPException as e:
            log.tree("Claim Timeout Update Failed", [
                ("Channel", self.channel.name),
                ("Error", str(e)),
            ], emoji="❌")
        except Exception as e:
            log.tree("Claim Timeout Error", [
                ("Channel", self.channel.name),
                ("Error", str(e)),
            ], emoji="❌")

    @ui.button(label="Approve", style=discord.ButtonStyle.secondary, emoji="<:allow:1455709499792031744>")
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        try:
            # Only owner can approve
            if interaction.user.id != self.owner.id:
                embed = discord.Embed(description="⚠️ Only the owner can respond to this request", color=COLOR_WARNING)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Claim Approve Rejected", [
                    ("Channel", self.channel.name),
                    ("Attempted By", str(interaction.user)),
                    ("Reason", "Not owner"),
                ], emoji="⚠️")
                return

            # Validate channel still exists
            channel = interaction.guild.get_channel(self.channel.id)
            if not channel:
                embed = discord.Embed(description="❌ Channel no longer exists", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
                log.tree("Claim Approve Failed", [
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
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
                log.tree("Claim Approve Failed", [
                    ("Channel", channel.name),
                    ("Requester", str(self.requester)),
                    ("Reason", "Requester left channel"),
                ], emoji="❌")
                return

            # Check if requester already owns a channel
            existing = db.get_owner_channel(requester.id, interaction.guild.id)
            if existing:
                embed = discord.Embed(
                    description=f"❌ **{requester.display_name}** already owns another channel",
                    color=COLOR_ERROR
                )
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
                log.tree("Claim Approve Failed", [
                    ("Channel", channel.name),
                    ("Requester", str(requester)),
                    ("Reason", "Already owns channel"),
                ], emoji="❌")
                return

            # Remove old owner permissions
            old_owner = interaction.guild.get_member(self.owner.id)
            if old_owner:
                await channel.set_permissions(old_owner, overwrite=None)

            # Give new owner full permissions (no move_members - use kick button instead)
            await channel.set_permissions(requester, connect=True, manage_channels=True, send_messages=True, read_message_history=True)
            db.transfer_ownership(channel.id, requester.id)

            embed = discord.Embed(
                description=f"✅ **{requester.display_name}** is now the owner",
                color=COLOR_SUCCESS
            )
            embed.set_thumbnail(url=requester.display_avatar.url)
            set_footer(embed)
            await interaction.response.edit_message(embed=embed, view=None)

            log.tree("Claim Approved", [
                ("Channel", channel.name),
                ("New Owner", str(requester)),
                ("Approved By", str(self.owner)),
            ], emoji="👑")

            # Webhook logging
            webhook_logger.log_tempvoice_claim(requester, self.owner, channel.name, approved=True)

            # Update panel
            if self.service:
                try:
                    await self.service._update_panel(channel)
                except Exception as e:
                    log.tree("Panel Update Failed", [
                        ("Channel", channel.name),
                        ("Context", "After claim approval"),
                        ("Error", str(e)),
                    ], emoji="⚠️")

        except discord.HTTPException as e:
            log.tree("Claim Approve Failed", [
                ("Channel", self.channel.name),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to process approval", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
        except Exception as e:
            log.tree("Claim Approve Error", [
                ("Channel", self.channel.name),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)

        self.stop()

    @ui.button(label="Deny", style=discord.ButtonStyle.secondary, emoji="<:block:1455709662316986539>")
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        try:
            # Only owner can deny
            if interaction.user.id != self.owner.id:
                embed = discord.Embed(description="⚠️ Only the owner can respond to this request", color=COLOR_WARNING)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Claim Deny Rejected", [
                    ("Channel", self.channel.name),
                    ("Attempted By", str(interaction.user)),
                    ("Reason", "Not owner"),
                ], emoji="⚠️")
                return

            embed = discord.Embed(
                description=f"❌ Claim request from **{self.requester.display_name}** denied",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.edit_message(embed=embed, view=None)

            log.tree("Claim Denied", [
                ("Channel", self.channel.name),
                ("Requester", str(self.requester)),
                ("Denied By", str(self.owner)),
            ], emoji="🚫")

            # Webhook logging
            webhook_logger.log_tempvoice_claim(self.requester, self.owner, self.channel.name, approved=False)

        except discord.HTTPException as e:
            log.tree("Claim Deny Failed", [
                ("Channel", self.channel.name),
                ("Error", str(e)),
            ], emoji="❌")
        except Exception as e:
            log.tree("Claim Deny Error", [
                ("Channel", self.channel.name),
                ("Error", str(e)),
            ], emoji="❌")

        self.stop()


class TempVoiceControlPanel(ui.View):
    """Control panel for temp voice channels."""

    def __init__(self, service: "TempVoiceService"):
        super().__init__(timeout=None)
        self.service = service

    async def _get_user_channel(self, interaction: discord.Interaction, log_context: str = "Action") -> Optional[discord.VoiceChannel]:
        """Get the user's temp voice channel."""
        channel_id = db.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            embed = discord.Embed(description="⚠️ You don't own a channel", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree(f"{log_context} Rejected", [
                ("User", str(interaction.user)),
                ("Reason", "No owned channel"),
            ], emoji="⚠️")
            return None

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            db.delete_temp_channel(channel_id)
            embed = discord.Embed(description="❌ Channel no longer exists", color=COLOR_ERROR)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.tree(f"{log_context} Failed", [
                ("User", str(interaction.user)),
                ("Channel ID", str(channel_id)),
                ("Reason", "Channel deleted"),
            ], emoji="❌")
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
                embed = discord.Embed(description="⚠️ You don't own a channel", color=COLOR_WARNING)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Lock Toggle Rejected", [
                    ("User", str(interaction.user)),
                    ("Reason", "No owned channel"),
                ], emoji="⚠️")
                return

            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                db.delete_temp_channel(channel_id)
                embed = discord.Embed(description="❌ Channel no longer exists", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Lock Toggle Failed", [
                    ("User", str(interaction.user)),
                    ("Channel ID", str(channel_id)),
                    ("Reason", "Channel deleted"),
                ], emoji="❌")
                return

            channel_info = db.get_temp_channel(channel.id)
            if not channel_info:
                embed = discord.Embed(description="❌ Channel data not found", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Lock Toggle Failed", [
                    ("User", str(interaction.user)),
                    ("Channel", channel.name),
                    ("Reason", "No DB record"),
                ], emoji="❌")
                return

            is_locked = channel_info.get("is_locked", 0)
            new_locked = 0 if is_locked else 1
            everyone = interaction.guild.default_role

            # Send response first, then do the work
            if new_locked:
                embed = discord.Embed(
                    description="<:lock:1455709111684694107> Channel is now **locked**",
                    color=COLOR_ERROR
                )
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                await channel.set_permissions(everyone, connect=False, send_messages=False, read_message_history=False)
            else:
                embed = discord.Embed(
                    description="<:unlock:1455709112309514290> Channel is now **unlocked**",
                    color=COLOR_SUCCESS
                )
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                await channel.set_permissions(everyone, connect=True, send_messages=False, read_message_history=False)

            db.update_temp_channel(channel.id, is_locked=new_locked)
            log.tree("Lock Toggled", [
                ("Channel", channel.name),
                ("Status", "Locked" if new_locked else "Unlocked"),
                ("By", str(interaction.user)),
            ], emoji="🔒" if new_locked else "🔓")

            # Webhook logging
            webhook_logger.log_tempvoice(
                interaction.user,
                "Lock" if new_locked else "Unlock",
                channel.name
            )

            # Update panel to reflect new state
            try:
                await self.service._update_panel(channel)
            except Exception as e:
                log.tree("Panel Update Failed", [
                    ("Channel", channel.name),
                    ("Context", "After lock toggle"),
                    ("Error", str(e)),
                ], emoji="⚠️")

        except discord.HTTPException as e:
            log.tree("Lock Toggle Failed", [
                ("By", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to update channel", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            log.tree("Lock Toggle Error", [
                ("By", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Limit", emoji="<:limit:1455709299732123762>", style=discord.ButtonStyle.secondary, custom_id="tv_limit", row=0)
    async def limit_button(self, interaction: discord.Interaction, button: ui.Button):
        """Set user limit."""
        try:
            channel = await self._get_user_channel(interaction, "Limit")
            if channel:
                await interaction.response.send_modal(LimitModal(channel))
        except discord.HTTPException as e:
            log.tree("Limit Button Failed", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to open limit modal", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            log.tree("Limit Button Error", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Rename", emoji="<:rename:1455709387711578394>", style=discord.ButtonStyle.secondary, custom_id="tv_rename", row=0)
    async def rename_button(self, interaction: discord.Interaction, button: ui.Button):
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
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Rename Blocked", [
                    ("User", str(interaction.user)),
                    ("Reason", "Not a booster"),
                ], emoji="💎")
                return

            channel = await self._get_user_channel(interaction, "Rename")
            if channel:
                await interaction.response.send_modal(NameModal(channel, interaction.user))
        except discord.HTTPException as e:
            log.tree("Rename Button Failed", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to open rename modal", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            log.tree("Rename Button Error", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    # Row 2: Permit, Block, Kick
    @ui.button(label="Allow", emoji="<:allow:1455709499792031744>", style=discord.ButtonStyle.secondary, custom_id="tv_permit", row=1)
    async def permit_button(self, interaction: discord.Interaction, button: ui.Button):
        """Permit/unpermit a user."""
        try:
            channel = await self._get_user_channel(interaction, "Allow")
            if channel:
                embed = discord.Embed(description="👤 Select user to allow (select again to remove)", color=COLOR_NEUTRAL)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, view=UserSelectView(channel, "permit", self.service), ephemeral=True)
        except discord.HTTPException as e:
            log.tree("Allow Button Failed", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to show user select", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            log.tree("Allow Button Error", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Block", emoji="<:block:1455709662316986539>", style=discord.ButtonStyle.secondary, custom_id="tv_block", row=1)
    async def block_button(self, interaction: discord.Interaction, button: ui.Button):
        """Block/unblock a user."""
        try:
            channel = await self._get_user_channel(interaction, "Block")
            if channel:
                embed = discord.Embed(description="🚫 Select user to block (select again to unblock)", color=COLOR_NEUTRAL)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, view=UserSelectView(channel, "block", self.service), ephemeral=True)
        except discord.HTTPException as e:
            log.tree("Block Button Failed", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to show user select", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            log.tree("Block Button Error", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Kick", emoji="<:kick:1455709879976198361>", style=discord.ButtonStyle.secondary, custom_id="tv_kick", row=1)
    async def kick_button(self, interaction: discord.Interaction, button: ui.Button):
        """Kick a user."""
        try:
            channel = await self._get_user_channel(interaction, "Kick")
            if channel:
                embed = discord.Embed(description="👢 Select user to kick from channel", color=COLOR_NEUTRAL)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, view=UserSelectView(channel, "kick"), ephemeral=True)
        except discord.HTTPException as e:
            log.tree("Kick Button Failed", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to show user select", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            log.tree("Kick Button Error", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    # Row 3: Claim, Transfer, Delete
    @ui.button(label="Claim", emoji="<:claim:1455709985467011173>", style=discord.ButtonStyle.secondary, custom_id="tv_claim", row=2)
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        """Request to claim channel - requires owner approval."""
        try:
            if not interaction.user.voice or not interaction.user.voice.channel:
                embed = discord.Embed(description="⚠️ Join a voice channel first", color=COLOR_WARNING)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Claim Rejected", [
                    ("User", str(interaction.user)),
                    ("Reason", "Not in voice channel"),
                ], emoji="⚠️")
                return

            channel = interaction.user.voice.channel
            channel_info = db.get_temp_channel(channel.id)

            if not channel_info:
                embed = discord.Embed(description="⚠️ Not a temp channel", color=COLOR_WARNING)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Claim Rejected", [
                    ("User", str(interaction.user)),
                    ("Channel", channel.name),
                    ("Reason", "Not a temp channel"),
                ], emoji="⚠️")
                return

            owner_id = channel_info["owner_id"]
            owner = interaction.guild.get_member(owner_id)

            # Can't claim your own channel
            if interaction.user.id == owner_id:
                embed = discord.Embed(description="⚠️ You already own this channel", color=COLOR_WARNING)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Claim Rejected", [
                    ("User", str(interaction.user)),
                    ("Channel", channel.name),
                    ("Reason", "Already owner"),
                ], emoji="⚠️")
                return

            existing = db.get_owner_channel(interaction.user.id, interaction.guild.id)
            if existing:
                embed = discord.Embed(description="⚠️ You already own a channel", color=COLOR_WARNING)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Claim Rejected", [
                    ("User", str(interaction.user)),
                    ("Channel", channel.name),
                    ("Reason", "Owns another channel"),
                ], emoji="⚠️")
                return

            # If owner left the server, allow instant claim
            if not owner:
                await channel.set_permissions(interaction.user, connect=True, manage_channels=True, send_messages=True, read_message_history=True)
                db.transfer_ownership(channel.id, interaction.user.id)
                embed = discord.Embed(
                    description=f"👑 You now own **{channel.name}**\nPrevious owner left the server",
                    color=COLOR_SUCCESS
                )
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                log.tree("Channel Claimed", [
                    ("Channel", channel.name),
                    ("New Owner", str(interaction.user)),
                    ("Previous Owner", f"User ID {owner_id} (left server)"),
                ], emoji="👑")

                # Webhook logging
                webhook_logger.log_tempvoice(interaction.user, "Instant Claim", channel.name)

                if self.service:
                    try:
                        await self.service._update_panel(channel)
                    except Exception as e:
                        log.tree("Panel Update Failed", [
                            ("Channel", channel.name),
                            ("Context", "After instant claim"),
                            ("Error", str(e)),
                        ], emoji="⚠️")
                return

            # Owner still exists - send approval request
            embed = discord.Embed(
                title="🔔 Claim Request",
                description=f"{interaction.user.mention} wants to claim this channel",
                color=0xfaa61a  # Orange/warning
            )
            embed.add_field(name="Requester", value=interaction.user.mention, inline=True)
            embed.add_field(name="Current Owner", value=owner.mention, inline=True)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            set_footer(embed)

            # Send approval request to channel, pinging owner
            view = ClaimApprovalView(channel, interaction.user, owner, self.service)
            await channel.send(content=owner.mention, embed=embed, view=view)

            response_embed = discord.Embed(
                description=f"📨 Claim request sent!\nWaiting for **{owner.display_name}** to approve...",
                color=COLOR_NEUTRAL
            )
            set_footer(response_embed)
            await interaction.response.send_message(embed=response_embed, ephemeral=True)

            log.tree("Claim Requested", [
                ("Channel", channel.name),
                ("Requester", str(interaction.user)),
                ("Owner", str(owner)),
            ], emoji="📨")

            # Webhook logging
            webhook_logger.log_tempvoice_claim(interaction.user, owner, channel.name, approved=None)

        except discord.HTTPException as e:
            log.tree("Claim Button Failed", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to process claim", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            log.tree("Claim Button Error", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Transfer", emoji="<:transfer:1455710226429902858>", style=discord.ButtonStyle.secondary, custom_id="tv_transfer", row=2)
    async def transfer_button(self, interaction: discord.Interaction, button: ui.Button):
        """Transfer ownership."""
        try:
            channel = await self._get_user_channel(interaction, "Transfer")
            if channel:
                embed = discord.Embed(description="🔄 Select new owner to transfer channel", color=COLOR_NEUTRAL)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, view=UserSelectView(channel, "transfer"), ephemeral=True)
        except discord.HTTPException as e:
            log.tree("Transfer Button Failed", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to show user select", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            log.tree("Transfer Button Error", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Delete", emoji="<:delete:1455710362539397192>", style=discord.ButtonStyle.secondary, custom_id="tv_delete", row=2)
    async def delete_button(self, interaction: discord.Interaction, button: ui.Button):
        """Delete channel."""
        try:
            channel = await self._get_user_channel(interaction, "Delete")
            if not channel:
                return

            # Count members that will be disconnected (excluding self)
            other_members = [m for m in channel.members if m.id != interaction.user.id]
            member_count = len(other_members)

            if member_count > 0:
                desc = f"🗑️ Delete **{channel.name}**?\n⚠️ {member_count} member{'s' if member_count != 1 else ''} will be disconnected"
            else:
                desc = f"🗑️ Delete **{channel.name}**?"

            embed = discord.Embed(
                description=desc,
                color=COLOR_ERROR,
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, view=ConfirmView("delete", channel), ephemeral=True)

        except discord.HTTPException as e:
            log.tree("Delete Button Failed", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ Failed to show confirmation", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            log.tree("Delete Button Error", [
                ("User", str(interaction.user)),
                ("Error", str(e)),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
