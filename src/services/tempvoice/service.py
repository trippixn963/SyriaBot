"""
TempVoice - Main Service
"""

import asyncio
import time
from typing import TYPE_CHECKING, Dict

import discord
from discord import ui

from src.core.config import config
from src.core.logger import log
from src.services.database import db
from src.utils.footer import set_footer
from .utils import generate_channel_name, is_booster
from .views import TempVoiceControlPanel

if TYPE_CHECKING:
    from src.bot import SyriaBot


# Cooldown between join-to-create attempts (seconds)
JOIN_COOLDOWN = 5

# Delay before auto-transfer when owner leaves (seconds)
OWNER_LEAVE_TRANSFER_DELAY = 30

# Number of messages before re-sending sticky control panel
STICKY_PANEL_MESSAGE_THRESHOLD = 20


class TempVoiceService:
    """Service for managing temporary voice channels."""

    def __init__(self, bot: "SyriaBot"):
        self.bot = bot
        self.control_panel = TempVoiceControlPanel(self)
        self._cleanup_task: asyncio.Task = None
        self._join_cooldowns: Dict[int, float] = {}  # user_id -> last join timestamp
        self._member_join_times: Dict[int, Dict[int, float]] = {}  # channel_id -> {user_id: join_time}
        self._pending_transfers: Dict[int, asyncio.Task] = {}  # channel_id -> pending transfer task
        self._message_counts: Dict[int, int] = {}  # channel_id -> message count since last panel

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
                log.tree("TempVoice Cleanup", [
                    ("Status", "Task cancelled"),
                ], emoji="🔇")
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
                log.tree("Orphan Channel Cleaned", [
                    ("Channel ID", str(channel_id)),
                    ("Reason", "Channel not in Discord"),
                ], emoji="🧹")
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
                except discord.HTTPException as e:
                    log.tree("Empty Channel Delete Failed", [
                        ("Channel ID", str(channel_id)),
                        ("Error", str(e)),
                    ], emoji="❌")

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
        message = await channel.send(embed=embed, view=self.control_panel)

        # Cache the panel message ID
        db.update_temp_channel(channel.id, panel_message_id=message.id)

        return message

    async def _update_panel(self, channel: discord.VoiceChannel) -> None:
        """Update the control panel embed in the channel using cached message ID."""
        channel_info = db.get_temp_channel(channel.id)
        if not channel_info:
            log.tree("Panel Update Skipped", [
                ("Channel ID", str(channel.id)),
                ("Reason", "No DB record"),
            ], emoji="⚠️")
            return

        owner = channel.guild.get_member(channel_info["owner_id"])
        if not owner:
            log.tree("Panel Update Skipped", [
                ("Channel", channel.name),
                ("Reason", "Owner not found"),
            ], emoji="⚠️")
            return

        is_locked = bool(channel_info.get("is_locked", 0))
        panel_message_id = channel_info.get("panel_message_id")

        # Try to use cached message ID first (fast path)
        if panel_message_id:
            try:
                message = await channel.fetch_message(panel_message_id)
                embed = self._build_panel_embed(channel, owner, is_locked)
                self._update_lock_button(is_locked)
                await message.edit(embed=embed, view=self.control_panel)
                return
            except discord.NotFound:
                log.tree("Panel Message Not Found", [
                    ("Channel", channel.name),
                    ("Message ID", str(panel_message_id)),
                    ("Action", "Will recreate"),
                ], emoji="⚠️")
            except discord.HTTPException as e:
                log.tree("Panel Update Failed", [
                    ("Channel", channel.name),
                    ("Error", str(e)),
                ], emoji="❌")

        # Fallback: Search through recent messages (slow path)
        panel_found = False
        try:
            async for message in channel.history(limit=15):
                if message.author.id == self.bot.user.id and message.embeds:
                    embed = self._build_panel_embed(channel, owner, is_locked)
                    self._update_lock_button(is_locked)
                    await message.edit(embed=embed, view=self.control_panel)
                    # Cache the message ID for next time
                    db.update_temp_channel(channel.id, panel_message_id=message.id)
                    panel_found = True
                    break
        except discord.HTTPException as e:
            log.tree("Panel History Search Failed", [
                ("Channel", channel.name),
                ("Error", str(e)),
            ], emoji="❌")

        # Panel was deleted - recreate it
        if not panel_found:
            try:
                embed = self._build_panel_embed(channel, owner, is_locked)
                self._update_lock_button(is_locked)
                message = await channel.send(embed=embed, view=self.control_panel)
                db.update_temp_channel(channel.id, panel_message_id=message.id)
                log.tree("Panel Recovered", [
                    ("Channel", channel.name),
                    ("Owner", str(owner)),
                ], emoji="🔧")
            except discord.HTTPException as e:
                log.tree("Panel Recovery Failed", [
                    ("Channel", channel.name),
                    ("Error", str(e)),
                ], emoji="❌")

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ) -> None:
        """Handle voice state updates."""
        # Safety check - ensure member and guild are valid
        if not member or not member.guild:
            log.tree("Voice State Update Skipped", [
                ("Reason", "Invalid member/guild"),
            ], emoji="⚠️")
            return

        # User left a VC - revoke text permissions
        if before.channel and before.channel.id != config.VC_CREATOR_CHANNEL_ID:
            # Skip ignored channels (managed by other bots, e.g. Quran VC)
            if before.channel.id not in config.VC_IGNORED_CHANNELS:
                # Re-fetch channel to ensure it still exists
                channel = member.guild.get_channel(before.channel.id)
                if channel:
                    await self._revoke_text_access(channel, member)
                    # Check if owner left - schedule delayed auto-transfer
                    if db.is_temp_channel(channel.id):
                        channel_info = db.get_temp_channel(channel.id)
                        if channel_info and channel_info["owner_id"] == member.id:
                            await self._schedule_owner_transfer(channel, member)
                        else:
                            # Non-owner left - check if empty
                            await self._check_empty_channel(channel)

        # User joined a VC - grant text permissions (works for dragged-in users too)
        if after.channel and after.channel.id != config.VC_CREATOR_CHANNEL_ID:
            # Skip ignored channels (managed by other bots, e.g. Quran VC)
            if after.channel.id in config.VC_IGNORED_CHANNELS:
                return
            # Re-fetch channel to ensure it still exists
            channel = member.guild.get_channel(after.channel.id)
            if channel:
                await self._grant_text_access(channel, member)
                # Owner rejoined - cancel pending transfer
                if channel.id in self._pending_transfers:
                    channel_info = db.get_temp_channel(channel.id)
                    if channel_info and channel_info["owner_id"] == member.id:
                        self._pending_transfers[channel.id].cancel()
                        del self._pending_transfers[channel.id]
                        log.tree("Owner Rejoined", [
                            ("Channel", channel.name),
                            ("Owner", str(member)),
                            ("Status", "Transfer cancelled"),
                        ], emoji="↩️")

        # User joined the creator channel - create new temp VC
        if after.channel and after.channel.id == config.VC_CREATOR_CHANNEL_ID:
            await self._create_temp_channel(member)

    async def on_message(self, message: discord.Message) -> None:
        """Handle messages in temp voice channels for sticky panel."""
        # Ignore bot messages and DMs
        if message.author.bot or not message.guild:
            return

        # Check if this is a voice channel (handles VoiceChannel and StageChannel)
        channel = message.channel
        if not hasattr(channel, 'voice_states'):
            return

        if not db.is_temp_channel(channel.id):
            return

        # Increment message count
        self._message_counts[channel.id] = self._message_counts.get(channel.id, 0) + 1

        # Check if we've hit the threshold
        if self._message_counts[channel.id] >= STICKY_PANEL_MESSAGE_THRESHOLD:
            # Reset count immediately to prevent spam if resend fails
            self._message_counts[channel.id] = 0
            await self._resend_sticky_panel(channel)

    async def _resend_sticky_panel(self, channel: discord.VoiceChannel) -> None:
        """Delete old panel and resend as sticky message."""
        channel_info = db.get_temp_channel(channel.id)
        if not channel_info:
            return

        owner = channel.guild.get_member(channel_info["owner_id"])
        if not owner:
            log.tree("Sticky Panel Skipped", [
                ("Channel", channel.name),
                ("Reason", "Owner not found"),
            ], emoji="⚠️")
            return

        # Try to delete old panel using cached message ID
        panel_message_id = channel_info.get("panel_message_id")
        if panel_message_id:
            try:
                old_message = await channel.fetch_message(panel_message_id)
                await old_message.delete()
            except discord.NotFound:
                log.tree("Sticky Panel Delete Skipped", [
                    ("Channel", channel.name),
                    ("Reason", "Already deleted"),
                ], emoji="⚠️")
            except discord.HTTPException as e:
                log.tree("Sticky Panel Delete Failed", [
                    ("Channel", channel.name),
                    ("Error", str(e)),
                ], emoji="❌")

        # Send new panel (preserves all stats like created_at from DB)
        try:
            is_locked = bool(channel_info.get("is_locked", 0))
            embed = self._build_panel_embed(channel, owner, is_locked)
            self._update_lock_button(is_locked)
            new_message = await channel.send(embed=embed, view=self.control_panel)

            # Cache new message ID
            db.update_temp_channel(channel.id, panel_message_id=new_message.id)

            log.tree("Sticky Panel Resent", [
                ("Channel", channel.name),
                ("Owner", str(owner)),
            ], emoji="📌")
        except discord.HTTPException as e:
            log.tree("Sticky Panel Failed", [
                ("Channel", channel.name),
                ("Error", str(e)),
            ], emoji="❌")

    async def _grant_text_access(self, channel: discord.VoiceChannel, member: discord.Member) -> None:
        """Grant text chat access to a member in a temp VC (includes dragged-in users)."""
        try:
            # Track join time for this member (for auto-transfer ordering)
            if channel.id not in self._member_join_times:
                self._member_join_times[channel.id] = {}
            if member.id not in self._member_join_times[channel.id]:
                self._member_join_times[channel.id][member.id] = time.time()

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
        except discord.HTTPException as e:
            log.tree("Text Access Grant Failed", [
                ("Channel", channel.name),
                ("User", str(member)),
                ("Error", str(e)),
            ], emoji="❌")
        except Exception as e:
            log.tree("Text Access Grant Error", [
                ("Channel", channel.name),
                ("User", str(member)),
                ("Error", str(e)),
            ], emoji="❌")

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

                # Clean up join time tracking for non-owner
                if channel.id in self._member_join_times:
                    self._member_join_times[channel.id].pop(member.id, None)

                # Check if user is trusted - they keep FULL access (text + connect)
                is_trusted = member.id in db.get_trusted_list(channel_info["owner_id"])

                if is_trusted:
                    # Trusted users keep connect AND text access even when not in VC
                    # No permission changes needed - they retain their allowed permissions
                    log.tree("Text Access Retained", [
                        ("Channel", channel.name),
                        ("User", str(member)),
                        ("Reason", "Trusted user"),
                    ], emoji="✅")
                else:
                    # Not trusted - remove all custom permissions
                    await channel.set_permissions(member, overwrite=None)

                # Update panel to show member left
                await self._update_panel(channel)
            else:
                # For non-temp channels - just remove the text permissions we granted
                await channel.set_permissions(member, overwrite=None)
        except discord.HTTPException as e:
            log.tree("Text Access Revoke Failed", [
                ("Channel", channel.name),
                ("User", str(member)),
                ("Error", str(e)),
            ], emoji="❌")
        except Exception as e:
            log.tree("Text Access Revoke Error", [
                ("Channel", channel.name),
                ("User", str(member)),
                ("Error", str(e)),
            ], emoji="❌")

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
            except discord.HTTPException as e:
                log.tree("Cooldown Disconnect Failed", [
                    ("User", str(member)),
                    ("Error", str(e)),
                ], emoji="❌")
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
                        await channel.set_permissions(new_owner, connect=True, manage_channels=True, send_messages=True, read_message_history=True)
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
                log.tree("Orphan DB Entry Cleaned", [
                    ("Channel ID", str(existing)),
                    ("Owner", str(member)),
                ], emoji="🧹")

        # Clean up stale trusted/blocked users (who left the server)
        guild_member_ids = {m.id for m in guild.members}
        stale_removed = db.cleanup_stale_users(member.id, guild_member_ids)
        if stale_removed > 0:
            log.tree("Stale User Cleanup", [
                ("Owner", str(member)),
                ("Entries Removed", str(stale_removed)),
                ("Reason", "Users left server"),
            ], emoji="🧹")

        # Get user settings for default limit
        settings = db.get_user_settings(member.id)
        default_limit = settings.get("default_limit", 0) if settings else 0

        # Generate channel name (uses shared utility)
        channel_name, name_source = generate_channel_name(member, guild)

        log.tree("Creating Channel", [
            ("Owner", str(member)),
            ("Name", channel_name),
            ("Source", name_source),
        ], emoji="🔧")

        # Get category
        category = None
        if config.VC_CATEGORY_ID:
            category = guild.get_channel(config.VC_CATEGORY_ID)
            if not category:
                log.tree("Category Not Found", [
                    ("Category ID", str(config.VC_CATEGORY_ID)),
                    ("Action", "Creating without category"),
                ], emoji="⚠️")

        try:
            # Build all overwrites upfront (single API call instead of multiple)
            overwrites = {
                # Lock by default + deny text access for everyone
                guild.default_role: discord.PermissionOverwrite(
                    connect=False,
                    send_messages=False,
                    read_message_history=False,
                ),
                # Owner permissions (full access including text, no move_members - use kick button)
                member: discord.PermissionOverwrite(
                    connect=True,
                    manage_channels=True,
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
                else:
                    log.tree("Mod Role Not Found", [
                        ("Role ID", str(config.MOD_ROLE_ID)),
                        ("Action", "Skipping mod permissions"),
                    ], emoji="⚠️")

            # Pre-build blocked user overwrites
            blocked_count = 0
            for blocked_id in db.get_blocked_list(member.id):
                blocked_user = guild.get_member(blocked_id)
                if blocked_user:
                    is_mod = any(r.id == config.MOD_ROLE_ID for r in blocked_user.roles)
                    if is_mod and member.id != config.OWNER_ID:
                        log.tree("Block Skipped", [
                            ("User", str(blocked_user)),
                            ("Reason", "Is moderator"),
                        ], emoji="⚠️")
                        continue
                    overwrites[blocked_user] = discord.PermissionOverwrite(connect=False)
                    blocked_count += 1

            # Pre-build trusted user overwrites (with permanent text access)
            trusted_count = 0
            for trusted_id in db.get_trusted_list(member.id):
                trusted_user = guild.get_member(trusted_id)
                if trusted_user:
                    overwrites[trusted_user] = discord.PermissionOverwrite(
                        connect=True,
                        send_messages=True,
                        read_message_history=True
                    )
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
        except Exception as e:
            log.tree("Channel Creation Error", [
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

            # Cancel any pending transfer
            if channel.id in self._pending_transfers:
                self._pending_transfers[channel.id].cancel()
                del self._pending_transfers[channel.id]

            # Clean up join times and message counts
            self._member_join_times.pop(channel.id, None)
            self._message_counts.pop(channel.id, None)

            db.delete_temp_channel(channel.id)
            try:
                await channel.delete(reason="Empty")
                log.tree("Channel Auto-Deleted", [
                    ("Channel", channel_name),
                    ("Owner ID", str(owner_id)),
                ], emoji="🗑️")
            except discord.HTTPException as e:
                log.tree("Empty Channel Delete Failed", [
                    ("Channel", channel_name),
                    ("Error", str(e)),
                ], emoji="❌")

    async def _schedule_owner_transfer(self, channel: discord.VoiceChannel, old_owner: discord.Member) -> None:
        """Schedule a delayed owner transfer when owner leaves the channel."""
        # Cancel any existing pending transfer for this channel
        if channel.id in self._pending_transfers:
            self._pending_transfers[channel.id].cancel()

        # Get remaining members (non-bot)
        remaining = [m for m in channel.members if not m.bot]
        if not remaining:
            # No one left to transfer to - check empty will handle deletion
            await self._check_empty_channel(channel)
            return

        log.tree("Owner Left Channel", [
            ("Channel", channel.name),
            ("Owner", str(old_owner)),
            ("Remaining Members", str(len(remaining))),
            ("Transfer Delay", f"{OWNER_LEAVE_TRANSFER_DELAY}s"),
        ], emoji="⏳")

        # Schedule the transfer
        task = asyncio.create_task(self._execute_owner_transfer(channel, old_owner))
        self._pending_transfers[channel.id] = task

    async def _execute_owner_transfer(self, channel: discord.VoiceChannel, old_owner: discord.Member) -> None:
        """Execute the delayed owner transfer after waiting."""
        try:
            # Wait before transferring
            await asyncio.sleep(OWNER_LEAVE_TRANSFER_DELAY)

            # Re-fetch channel to ensure it still exists
            channel = old_owner.guild.get_channel(channel.id)
            if not channel:
                log.tree("Transfer Cancelled", [
                    ("Reason", "Channel no longer exists"),
                ], emoji="❌")
                return

            # Check if channel is still a temp channel
            channel_info = db.get_temp_channel(channel.id)
            if not channel_info:
                log.tree("Transfer Cancelled", [
                    ("Channel", channel.name),
                    ("Reason", "No longer a temp channel"),
                ], emoji="❌")
                return

            # Check if owner is back
            if any(m.id == channel_info["owner_id"] for m in channel.members):
                log.tree("Transfer Cancelled", [
                    ("Channel", channel.name),
                    ("Reason", "Owner is back in channel"),
                ], emoji="↩️")
                return

            # Get remaining members (non-bot)
            remaining = [m for m in channel.members if not m.bot]
            if not remaining:
                # No one left - delete channel
                await self._check_empty_channel(channel)
                return

            # Find the longest-in-channel member based on join times
            join_times = self._member_join_times.get(channel.id, {})
            if join_times:
                # Sort by join time (oldest first)
                sorted_members = sorted(
                    [(m, join_times.get(m.id, float('inf'))) for m in remaining],
                    key=lambda x: x[1]
                )
                new_owner = sorted_members[0][0]
            else:
                # Fallback: first remaining member
                new_owner = remaining[0]

            # Execute the transfer
            await self._apply_owner_transfer(channel, old_owner, new_owner)

        except asyncio.CancelledError:
            log.tree("Transfer Cancelled", [
                ("Channel", channel.name if channel else "Unknown"),
                ("Reason", "Task cancelled (owner likely rejoined)"),
            ], emoji="↩️")
        except Exception as e:
            log.tree("Transfer Error", [
                ("Channel", channel.name if channel else "Unknown"),
                ("Error", str(e)),
            ], emoji="❌")
        finally:
            # Clean up the pending transfer entry
            self._pending_transfers.pop(channel.id, None)

    async def _apply_owner_transfer(
        self,
        channel: discord.VoiceChannel,
        old_owner: discord.Member,
        new_owner: discord.Member
    ) -> None:
        """Apply the ownership transfer to a new owner with their settings."""
        try:
            guild = channel.guild

            # Get old owner's current permissions
            old_owner_member = guild.get_member(old_owner.id)
            if old_owner_member:
                await channel.set_permissions(old_owner_member, overwrite=None)

            # Grant new owner full permissions (no move_members - use kick button)
            await channel.set_permissions(
                new_owner,
                connect=True,
                manage_channels=True,
                send_messages=True,
                read_message_history=True
            )

            # Update DB ownership
            db.transfer_ownership(channel.id, new_owner.id)

            # Generate channel name for new owner (uses shared utility)
            channel_name, name_source = generate_channel_name(new_owner, guild)

            await channel.edit(name=channel_name)
            db.update_temp_channel(channel.id, name=channel_name)

            # Apply new owner's blocked list
            blocked_count = 0
            for blocked_id in db.get_blocked_list(new_owner.id):
                blocked_user = guild.get_member(blocked_id)
                if blocked_user:
                    # Skip mods unless new owner is developer
                    is_mod = any(r.id == config.MOD_ROLE_ID for r in blocked_user.roles)
                    if is_mod and new_owner.id != config.OWNER_ID:
                        continue
                    await channel.set_permissions(blocked_user, connect=False)
                    # Kick if in channel
                    if blocked_user.voice and blocked_user.voice.channel == channel:
                        try:
                            await blocked_user.move_to(None)
                        except discord.HTTPException as e:
                            log.tree("Blocked User Kick Failed", [
                                ("Channel", channel.name),
                                ("User", str(blocked_user)),
                                ("Error", str(e)),
                            ], emoji="❌")
                    blocked_count += 1

            # Apply new owner's trusted list (with text permissions)
            trusted_count = 0
            for trusted_id in db.get_trusted_list(new_owner.id):
                trusted_user = guild.get_member(trusted_id)
                if trusted_user:
                    await channel.set_permissions(
                        trusted_user,
                        connect=True,
                        send_messages=True,
                        read_message_history=True
                    )
                    trusted_count += 1

            # Notify new owner in channel chat
            try:
                notification = await channel.send(
                    f"<:transfer:1455710226429902858> {new_owner.mention} you are now the owner of this channel!\n"
                    f"*The previous owner left and you were here the longest.*"
                )
                # Auto-delete notification after 30 seconds
                await asyncio.sleep(30)
                try:
                    await notification.delete()
                except discord.HTTPException as e:
                    log.tree("Notification Delete Failed", [
                        ("Channel", channel.name),
                        ("Error", str(e)),
                    ], emoji="⚠️")
            except discord.HTTPException as e:
                log.tree("Transfer Notification Failed", [
                    ("Channel", channel.name),
                    ("New Owner", str(new_owner)),
                    ("Error", str(e)),
                ], emoji="❌")

            # Update the control panel
            await self._update_panel(channel)

            log.tree("Auto-Transfer Complete", [
                ("Channel", channel_name),
                ("From", str(old_owner)),
                ("To", str(new_owner)),
                ("Name Source", name_source),
                ("Allowed Applied", str(trusted_count)),
                ("Blocked Applied", str(blocked_count)),
            ], emoji="🔄")

        except discord.HTTPException as e:
            log.tree("Auto-Transfer Failed", [
                ("Channel", channel.name),
                ("From", str(old_owner)),
                ("To", str(new_owner)),
                ("Error", str(e)),
            ], emoji="❌")
        except Exception as e:
            log.tree("Auto-Transfer Error", [
                ("Channel", channel.name),
                ("Error", str(e)),
            ], emoji="❌")
