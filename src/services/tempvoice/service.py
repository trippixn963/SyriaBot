"""
TempVoice - Main Service
"""

import asyncio
import time
from typing import TYPE_CHECKING, Dict

import discord
from discord import ui

from src.core.config import config
from src.core.constants import (
    TEMPVOICE_JOIN_COOLDOWN,
    TEMPVOICE_OWNER_LEAVE_TRANSFER_DELAY,
    TEMPVOICE_STICKY_PANEL_THRESHOLD,
    TEMPVOICE_REORDER_DEBOUNCE_DELAY,
)
from src.core.logger import log
from src.services.database import db
from src.utils.footer import set_footer
from .utils import (
    generate_base_name,
    build_full_name,
    extract_base_name,
    is_booster,
    get_owner_overwrite,
    set_owner_permissions,
    get_trusted_overwrite,
    get_blocked_overwrite,
    get_locked_overwrite,
)
from .views import TempVoiceControlPanel

if TYPE_CHECKING:
    from src.bot import SyriaBot

# Aliases for backwards compatibility
JOIN_COOLDOWN = TEMPVOICE_JOIN_COOLDOWN
OWNER_LEAVE_TRANSFER_DELAY = TEMPVOICE_OWNER_LEAVE_TRANSFER_DELAY
STICKY_PANEL_MESSAGE_THRESHOLD = TEMPVOICE_STICKY_PANEL_THRESHOLD
REORDER_DEBOUNCE_DELAY = TEMPVOICE_REORDER_DEBOUNCE_DELAY


class TempVoiceService:
    """Service for managing temporary voice channels."""

    def __init__(self, bot: "SyriaBot") -> None:
        """Initialize TempVoice service with bot reference and control panel."""
        self.bot = bot
        self.control_panel = TempVoiceControlPanel(self)
        self._cleanup_task: asyncio.Task = None
        self._join_cooldowns: Dict[int, float] = {}  # user_id -> last join timestamp
        self._member_join_times: Dict[int, Dict[int, float]] = {}  # channel_id -> {user_id: join_time}
        self._pending_transfers: Dict[int, asyncio.Task] = {}  # channel_id -> pending transfer task
        self._message_counts: Dict[int, int] = {}  # channel_id -> message count since last panel
        self._create_lock = asyncio.Lock()  # Prevents race conditions when multiple users join at once
        self._pending_reorders: Dict[int, asyncio.Task] = {}  # guild_id -> pending reorder task (debounced)
        self._panel_locks: Dict[int, asyncio.Lock] = {}  # channel_id -> lock for panel updates

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
        await self._strip_manage_channels()  # One-time fix for existing channels

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
        cancelled_tasks = []

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                cancelled_tasks.append("cleanup")

        # Cancel all pending transfer tasks
        for channel_id, task in list(self._pending_transfers.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                cancelled_tasks.append(f"transfer-{channel_id}")
        self._pending_transfers.clear()

        # Cancel all pending reorder tasks
        for guild_id, task in list(self._pending_reorders.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                cancelled_tasks.append(f"reorder-{guild_id}")
        self._pending_reorders.clear()

        log.tree("TempVoice Service Stopped", [
            ("Cancelled Tasks", str(len(cancelled_tasks))),
        ], emoji="🔇")

    async def _periodic_cleanup(self) -> None:
        """Periodically clean up empty temp channels."""
        while True:
            await asyncio.sleep(config.VC_CLEANUP_INTERVAL)
            try:
                await self._cleanup_empty_channels()
            except Exception as e:
                log.error_tree("Periodic Cleanup Failed", e)

    async def _cleanup_empty_channels(self) -> None:
        """Scan and delete empty temp channels (handles missed deletions)."""
        channels = db.get_all_temp_channels()
        cleaned = 0
        guilds_affected: set[int] = set()  # Track guilds that need reordering

        # Build protected set: creator channel + any configured protected channels
        protected = set(config.VC_PROTECTED_CHANNELS)
        if config.VC_CREATOR_CHANNEL_ID:
            protected.add(config.VC_CREATOR_CHANNEL_ID)

        for channel_data in channels:
            channel_id = channel_data["channel_id"]
            guild_id = channel_data.get("guild_id")

            # Skip protected channels
            if channel_id in protected:
                continue

            channel = self.bot.get_channel(channel_id)

            # Channel doesn't exist in Discord - clean up DB
            if not channel:
                db.delete_temp_channel(channel_id)
                cleaned += 1
                if guild_id:
                    guilds_affected.add(guild_id)
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
                    guilds_affected.add(channel.guild.id)
                    log.tree("Empty Channel Cleaned", [
                        ("Channel", channel_name),
                        ("Reason", "Periodic cleanup"),
                    ], emoji="🧹")
                except discord.HTTPException as e:
                    log.error_tree("Empty Channel Delete Failed", e, [
                        ("Channel ID", str(channel_id)),
                    ])

        if cleaned > 0:
            log.tree("Periodic Cleanup Complete", [
                ("Channels Removed", str(cleaned)),
            ], emoji="🧹")

            # Schedule reorder for affected guilds (debounced)
            for guild_id in guilds_affected:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    self.schedule_reorder(guild)

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

    async def _strip_manage_channels(self) -> None:
        """Strip manage_channels from all channel owners (one-time migration)."""
        channels = db.get_all_temp_channels()
        total = len(channels)
        fixed = 0
        skipped = 0
        errors = 0

        log.tree("Permission Migration Starting", [
            ("Channels", str(total)),
            ("Action", "Checking manage_channels permissions"),
        ], emoji="🔒")

        for channel_data in channels:
            channel = self.bot.get_channel(channel_data["channel_id"])
            if not channel or not isinstance(channel, discord.VoiceChannel):
                skipped += 1
                continue

            owner = channel.guild.get_member(channel_data["owner_id"])
            if not owner:
                skipped += 1
                continue

            # Check if owner has manage_channels permission
            current_overwrite = channel.overwrites_for(owner)
            if current_overwrite.manage_channels is not True:
                continue

            # Strip manage_channels
            try:
                await set_owner_permissions(channel, owner)
                fixed += 1
                log.tree("Permission Fixed", [
                    ("Channel", channel.name),
                    ("Channel ID", str(channel.id)),
                    ("Owner", f"{owner.name} ({owner.display_name})"),
                    ("Owner ID", str(owner.id)),
                    ("Action", "Removed manage_channels"),
                ], emoji="🔧")
            except discord.HTTPException as e:
                errors += 1
                log.error_tree("Permission Fix Failed", e, [
                    ("Channel", channel.name),
                    ("Channel ID", str(channel_data["channel_id"])),
                    ("Owner ID", str(channel_data["owner_id"])),
                ])

        log.tree("Permission Migration Complete", [
            ("Total Channels", str(total)),
            ("Fixed", str(fixed)),
            ("Skipped", str(skipped)),
            ("Errors", str(errors)),
        ], emoji="✅" if errors == 0 else "⚠️")

    def _build_panel_embed(
        self,
        channel: discord.VoiceChannel,
        owner: discord.Member,
        is_locked: bool = True
    ) -> discord.Embed:
        """Build the control panel embed."""
        channel_info = db.get_temp_channel(channel.id)
        owner_id = channel_info["owner_id"] if channel_info else owner.id

        # Get both lists in single DB call (optimization)
        trusted_list, blocked_list = db.get_user_access_lists(owner_id)

        # Validate trusted users still exist in guild
        valid_trusted = [
            (uid, m) for uid in trusted_list
            if (m := channel.guild.get_member(uid))
        ]

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

    def _get_panel_lock(self, channel_id: int) -> asyncio.Lock:
        """Get or create a lock for panel updates on a specific channel."""
        if channel_id not in self._panel_locks:
            self._panel_locks[channel_id] = asyncio.Lock()
        return self._panel_locks[channel_id]

    async def _update_panel(self, channel: discord.VoiceChannel) -> None:
        """Update the control panel embed in the channel using cached message ID."""
        # Use per-channel lock to prevent duplicate panels from concurrent updates
        lock = self._get_panel_lock(channel.id)
        async with lock:
            await self._update_panel_inner(channel)

    async def _update_panel_inner(self, channel: discord.VoiceChannel) -> None:
        """Inner panel update logic (called with lock held)."""
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
                log.error_tree("Panel Update Failed", e, [
                    ("Channel", channel.name),
                ])

        # Fallback: Search through recent messages (slow path)
        panel_found = False
        try:
            # Safety check - bot.user can be None during startup
            if not self.bot.user:
                log.tree("Panel Update Skipped", [
                    ("Channel", channel.name),
                    ("Reason", "Bot not ready"),
                ], emoji="⚠️")
                return

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
            log.error_tree("Panel History Search Failed", e, [
                ("Channel", channel.name),
            ])

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
                log.error_tree("Panel Recovery Failed", e, [
                    ("Channel", channel.name),
                ])

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

        # Determine if user actually changed channels (ignore mute/deafen/stream changes)
        left_channel = before.channel and (not after.channel or before.channel.id != after.channel.id)
        joined_channel = after.channel and (not before.channel or after.channel.id != before.channel.id)

        # User left a VC - revoke text permissions
        if left_channel and before.channel.id != config.VC_CREATOR_CHANNEL_ID:
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
        if joined_channel and after.channel.id != config.VC_CREATOR_CHANNEL_ID:
            # Skip ignored channels (managed by other bots, e.g. Quran VC)
            if after.channel.id in config.VC_IGNORED_CHANNELS:
                return
            # Re-fetch channel to ensure it still exists
            channel = member.guild.get_channel(after.channel.id)
            if channel:
                await self._grant_text_access(channel, member)
                # Owner rejoined - cancel pending transfer
                channel_info = db.get_temp_channel(channel.id)
                if channel_info and channel_info["owner_id"] == member.id:
                    task = self._pending_transfers.pop(channel.id, None)
                    if task:
                        task.cancel()
                        log.tree("Owner Rejoined", [
                            ("Channel", channel.name),
                            ("Owner", f"{member.name} ({member.display_name})"),
                            ("Owner ID", str(member.id)),
                            ("Status", "Transfer cancelled"),
                        ], emoji="↩️")

                # Check if owner's channel needs renaming (lost booster status)
                await self._check_booster_name(channel, member)

        # User joined the creator channel - create new temp VC
        if joined_channel and after.channel.id == config.VC_CREATOR_CHANNEL_ID:
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
        # Use per-channel lock to prevent races with _update_panel
        lock = self._get_panel_lock(channel.id)
        async with lock:
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
                    log.error_tree("Sticky Panel Delete Failed", e, [
                        ("Channel", channel.name),
                    ])

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
                log.error_tree("Sticky Panel Failed", e, [
                    ("Channel", channel.name),
                ])

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
            log.error_tree("Text Access Grant Failed", e, [
                ("Channel", channel.name),
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])
        except Exception as e:
            log.error_tree("Text Access Grant Error", e, [
                ("Channel", channel.name),
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])

    async def _check_booster_name(self, channel: discord.VoiceChannel, member: discord.Member) -> None:
        """Check if owner lost booster status and needs channel renamed."""
        try:
            # Fast check: skip if not in temp voice category (no DB call needed)
            if not channel.category or channel.category_id != config.VC_CATEGORY_ID:
                return

            channel_info = db.get_temp_channel(channel.id)
            if not channel_info:
                return

            # Only check for the owner
            if channel_info["owner_id"] != member.id:
                return

            # If they're still a booster, no action needed
            if is_booster(member):
                return

            # Non-booster should have display_name as base name (not custom)
            expected_base = member.display_name[:80]
            current_base = channel_info.get("base_name") or extract_base_name(channel.name)

            # If name is correct, no action needed
            if current_base == expected_base:
                return

            # Rename to display name
            position = self._get_channel_position(channel)
            expected_name = build_full_name(position, expected_base)
            old_name = channel.name
            await channel.edit(name=expected_name)
            db.update_temp_channel(channel.id, name=expected_name, base_name=expected_base)

            log.tree("Channel Renamed (Lost Booster)", [
                ("Channel", channel.name),
                ("From", old_name),
                ("To", expected_name),
                ("Owner", f"{member.name} ({member.display_name})"),
                ("Owner ID", str(member.id)),
            ], emoji="💎")

            await self._update_panel(channel)

        except discord.HTTPException as e:
            log.error_tree("Booster Name Check Failed", e, [
                ("Channel", channel.name),
                ("Channel ID", str(channel.id)),
                ("Member", f"{member.name} ({member.display_name})"),
                ("Member ID", str(member.id)),
            ])
        except Exception as e:
            log.error_tree("Booster Name Check Error", e, [
                ("Channel", channel.name),
                ("Channel ID", str(channel.id)),
                ("Member", f"{member.name} ({member.display_name})"),
                ("Member ID", str(member.id)),
            ])

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
                        ("User", f"{member.name} ({member.display_name})"),
                        ("ID", str(member.id)),
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
            log.error_tree("Text Access Revoke Failed", e, [
                ("Channel", channel.name),
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])
        except Exception as e:
            log.error_tree("Text Access Revoke Error", e, [
                ("Channel", channel.name),
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])

    def schedule_reorder(self, guild: discord.Guild) -> None:
        """
        Schedule a debounced channel reorder for a guild.

        If multiple deletions happen quickly (bulk cleanup), this ensures
        we only reorder once after all deletions are done.

        Non-blocking - fires and forgets the background task.
        """
        guild_id = guild.id

        # Cancel any existing pending reorder for this guild (race-safe)
        existing_task = self._pending_reorders.pop(guild_id, None)
        if existing_task:
            existing_task.cancel()
            log.tree("Reorder Rescheduled", [
                ("Guild", guild.name),
                ("Reason", "New deletion during debounce"),
            ], emoji="🔄")

        # Schedule new reorder after debounce delay
        task = asyncio.create_task(self._debounced_reorder(guild))
        self._pending_reorders[guild_id] = task

        if not existing_task:
            log.tree("Reorder Scheduled", [
                ("Guild", guild.name),
                ("Delay", f"{REORDER_DEBOUNCE_DELAY}s"),
            ], emoji="📋")

    async def _debounced_reorder(self, guild: discord.Guild) -> None:
        """Wait for debounce delay, then execute reorder."""
        try:
            await asyncio.sleep(REORDER_DEBOUNCE_DELAY)
            await self._reorder_channels(guild)
        except asyncio.CancelledError:
            # Another reorder was scheduled, this one is cancelled (already logged in schedule_reorder)
            pass
        except Exception as e:
            log.error_tree("Debounced Reorder Error", e, [
                ("Guild", guild.name),
            ])
        finally:
            # Clean up the pending task reference
            self._pending_reorders.pop(guild.id, None)

    async def _reorder_channels(self, guild: discord.Guild) -> None:
        """
        Reorder all temp voice channels in the category by position.
        Updates channel names to have sequential Roman numerals (I, II, III...).

        Optimized with batch DB query for high-traffic servers.
        """
        if not config.VC_CATEGORY_ID:
            return

        category = guild.get_channel(config.VC_CATEGORY_ID)
        if not category:
            return

        # Get all voice channels in category, sorted by position (top to bottom)
        voice_channels = sorted(
            [ch for ch in category.voice_channels if ch.id != config.VC_CREATOR_CHANNEL_ID],
            key=lambda c: c.position
        )

        if not voice_channels:
            return

        # OPTIMIZATION: Batch fetch all temp channel data in one DB call
        all_temp_channels = db.get_all_temp_channels(guild.id)
        temp_channel_map = {tc["channel_id"]: tc for tc in all_temp_channels}

        # Track channels that need renaming
        channels_to_rename = []

        # Track position separately - only increment for actual temp channels
        position = 0
        for channel in voice_channels:
            channel_info = temp_channel_map.get(channel.id)
            if not channel_info:
                continue  # Skip non-temp channels without consuming a position

            position += 1  # Only count actual temp channels

            # Get or extract base name
            base_name = channel_info.get("base_name")
            if not base_name:
                # Migration: extract from current channel name
                base_name = extract_base_name(channel.name)
                db.update_temp_channel(channel.id, base_name=base_name)

            # Build expected name for this position
            expected_name = build_full_name(position, base_name)

            # Check if rename is needed
            if channel.name != expected_name:
                channels_to_rename.append((channel, expected_name, position, base_name))

        if not channels_to_rename:
            return

        log.tree("Reordering Channels", [
            ("Count", str(len(channels_to_rename))),
            ("Total VCs", str(len(voice_channels))),
            ("Category", category.name),
        ], emoji="🔢")

        # Rename channels with small delay to avoid rate limits
        renamed_count = 0
        for channel, new_name, position, base_name in channels_to_rename:
            try:
                old_name = channel.name
                await channel.edit(name=new_name)
                db.update_temp_channel(channel.id, name=new_name)
                renamed_count += 1

                # Only log individual renames if few channels (avoid log spam)
                if len(channels_to_rename) <= 3:
                    log.tree("Channel Renumbered", [
                        ("From", old_name),
                        ("To", new_name),
                        ("Position", str(position)),
                    ], emoji="🔢")

                # Small delay to avoid rate limits
                await asyncio.sleep(0.3)

            except discord.HTTPException as e:
                log.error_tree("Reorder Rename Failed", e, [
                    ("Channel", channel.name),
                    ("Target", new_name),
                ])
            except Exception as e:
                log.error_tree("Reorder Error", e, [
                    ("Channel", channel.name),
                ])

        # Summary log for bulk renames
        if len(channels_to_rename) > 3:
            log.tree("Reorder Complete", [
                ("Renamed", f"{renamed_count}/{len(channels_to_rename)}"),
                ("Category", category.name),
            ], emoji="✅")

    def _get_next_position(self, guild: discord.Guild) -> int:
        """Get the next position number for a new temp channel."""
        if not config.VC_CATEGORY_ID:
            return 1

        category = guild.get_channel(config.VC_CATEGORY_ID)
        if not category:
            return 1

        # Count existing temp voice channels (excluding creator channel)
        temp_channels = [
            ch for ch in category.voice_channels
            if ch.id != config.VC_CREATOR_CHANNEL_ID and db.is_temp_channel(ch.id)
        ]

        return len(temp_channels) + 1

    def _get_channel_position(self, channel: discord.VoiceChannel) -> int:
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

    async def _create_temp_channel(self, member: discord.Member) -> None:
        """Create a new temp voice channel for a member."""
        # Check if lock is already held (someone else is creating)
        if self._create_lock.locked():
            log.tree("Create Queued", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Status", "Waiting for previous creation to complete"),
            ], emoji="⏳")

        # Use lock to prevent race conditions when multiple users join at once
        async with self._create_lock:
            log.tree("Create Lock Acquired", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ], emoji="🔓")
            await self._create_temp_channel_inner(member)

    async def _create_temp_channel_inner(self, member: discord.Member) -> None:
        """Inner method for channel creation (called within lock)."""
        guild = member.guild
        member_id = member.id

        log.tree("Create Inner Started", [
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
            ("Guild", guild.name),
        ], emoji="🔧")

        # Re-fetch member to get current voice state (cache may be stale after waiting for lock)
        try:
            member = guild.get_member(member_id)
            if not member:
                log.tree("Create Skipped", [
                    ("User ID", str(member_id)),
                    ("Reason", "Member not found in guild"),
                ], emoji="⏭️")
                return
            # Build clean voice state info
            if member.voice and member.voice.channel:
                channel_name = member.voice.channel.name
                states = []
                if member.voice.self_mute:
                    states.append("Muted")
                if member.voice.self_deaf:
                    states.append("Deafened")
                state_str = ", ".join(states) if states else "Normal"
            else:
                channel_name = "None"
                state_str = "N/A"

            log.tree("Member Refetched", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Channel", channel_name),
                ("State", state_str),
            ], emoji="🔍")
        except Exception as e:
            log.error_tree("Create Member Fetch Failed", e, [
                ("User ID", str(member_id)),
            ])
            return

        # Check if user is still in creator channel (they may have left while waiting for lock)
        if not member.voice or not member.voice.channel:
            log.tree("Create Skipped", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Reason", "User no longer in any voice channel"),
            ], emoji="⏭️")
            return

        if member.voice.channel.id != config.VC_CREATOR_CHANNEL_ID:
            log.tree("Create Skipped", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Current Channel", member.voice.channel.name),
                ("Reason", "User moved to different channel while waiting"),
            ], emoji="⏭️")
            return

        # Check cooldown to prevent spam
        now = time.time()
        last_join = self._join_cooldowns.get(member.id, 0)
        if now - last_join < JOIN_COOLDOWN:
            remaining = JOIN_COOLDOWN - (now - last_join)
            log.tree("Join Cooldown", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Remaining", f"{remaining:.1f}s"),
            ], emoji="⏳")
            # Disconnect them from creator channel
            try:
                await member.move_to(None)
            except discord.HTTPException as e:
                log.error_tree("Cooldown Disconnect Failed", e, [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                ])
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
                        await set_owner_permissions(channel, new_owner)
                        db.transfer_ownership(channel.id, new_owner.id)
                        log.tree("Auto-Transfer", [
                            ("Channel", channel.name),
                            ("From", f"{member.name} ({member.display_name})"),
                            ("From ID", str(member.id)),
                            ("To", f"{new_owner.name} ({new_owner.display_name})"),
                            ("To ID", str(new_owner.id)),
                        ], emoji="🔄")
                    except discord.HTTPException as e:
                        log.error_tree("Auto-Transfer Failed", e, [
                            ("Channel", channel.name),
                            ("From", f"{member.name} ({member.display_name})"),
                            ("From ID", str(member.id)),
                            ("To", f"{new_owner.name} ({new_owner.display_name})"),
                            ("To ID", str(new_owner.id)),
                        ])
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
                        log.error_tree("Auto-Delete Failed", e, [
                            ("Channel", channel.name),
                            ("Owner", f"{member.name} ({member.display_name})"),
                            ("Owner ID", str(member.id)),
                        ])
            else:
                db.delete_temp_channel(existing)
                log.tree("Orphan DB Entry Cleaned", [
                    ("Channel ID", str(existing)),
                    ("Owner", f"{member.name} ({member.display_name})"),
                    ("Owner ID", str(member.id)),
                ], emoji="🧹")

        # Clean up stale trusted/blocked users (who left the server)
        guild_member_ids = {m.id for m in guild.members}
        stale_removed = db.cleanup_stale_users(member.id, guild_member_ids)
        if stale_removed > 0:
            log.tree("Stale User Cleanup", [
                ("Owner", f"{member.name} ({member.display_name})"),
                ("Owner ID", str(member.id)),
                ("Entries Removed", str(stale_removed)),
                ("Reason", "Users left server"),
            ], emoji="🧹")

        # Get user settings for default limit
        settings = db.get_user_settings(member.id)
        default_limit = settings.get("default_limit", 0) if settings else 0

        # Generate channel name with position-based numbering
        base_name, name_source = generate_base_name(member)
        position = self._get_next_position(guild)
        channel_name = build_full_name(position, base_name)

        log.tree("Creating Channel", [
            ("Owner", f"{member.name} ({member.display_name})"),
            ("Owner ID", str(member.id)),
            ("Name", channel_name),
            ("Base Name", base_name),
            ("Position", str(position)),
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
                guild.default_role: get_locked_overwrite(),
                # Owner permissions (no manage_channels - use bot's rename button)
                member: get_owner_overwrite(),
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
                            ("User", f"{blocked_user.name} ({blocked_user.display_name})"),
                            ("ID", str(blocked_user.id)),
                            ("Reason", "Is moderator"),
                        ], emoji="⚠️")
                        continue
                    overwrites[blocked_user] = get_blocked_overwrite()
                    blocked_count += 1

            # Pre-build trusted user overwrites (with permanent text access)
            trusted_count = 0
            for trusted_id in db.get_trusted_list(member.id):
                trusted_user = guild.get_member(trusted_id)
                if trusted_user:
                    overwrites[trusted_user] = get_trusted_overwrite()
                    trusted_count += 1

            # Create channel with ALL permissions in one API call
            channel = await guild.create_voice_channel(
                name=channel_name,
                category=category,
                user_limit=default_limit,
                overwrites=overwrites,
                reason=f"TempVoice for {member}"
            )

            # Store in database (locked by default, with base_name for reordering)
            db.create_temp_channel(channel.id, member.id, guild.id, channel_name)
            db.update_temp_channel(channel.id, is_locked=1, base_name=base_name)

            # Move user
            try:
                await member.move_to(channel)
            except discord.HTTPException as e:
                log.error_tree("Move User Failed", e, [
                    ("Channel", channel_name),
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                ])
                # Channel was created but move failed - clean up
                db.delete_temp_channel(channel.id)
                await channel.delete(reason="Failed to move user")
                return

            # Send control panel with applied counts
            try:
                await self._send_channel_interface(channel, member, trusted_count, blocked_count)
            except Exception as e:
                log.error_tree("Panel Send Failed", e, [
                    ("Channel", channel_name),
                ])

            log.tree("Channel Created", [
                ("Channel", channel_name),
                ("Owner", f"{member.name} ({member.display_name})"),
                ("Owner ID", str(member.id)),
                ("Allowed Applied", str(trusted_count)),
                ("Blocked Applied", str(blocked_count)),
            ], emoji="🔊")

        except discord.HTTPException as e:
            log.error_tree("Channel Creation Failed", e, [
                ("Owner", f"{member.name} ({member.display_name})"),
                ("Owner ID", str(member.id)),
            ])
        except Exception as e:
            log.error_tree("Channel Creation Error", e, [
                ("Owner", f"{member.name} ({member.display_name})"),
                ("Owner ID", str(member.id)),
            ])

    async def _check_empty_channel(self, channel: discord.VoiceChannel) -> None:
        """Check if channel is empty and should be deleted."""
        if not db.is_temp_channel(channel.id):
            return

        if len(channel.members) == 0:
            channel_name = channel.name
            channel_info = db.get_temp_channel(channel.id)
            owner_id = channel_info["owner_id"] if channel_info else "Unknown"
            guild = channel.guild  # Save before deletion

            # Cancel any pending transfer
            if channel.id in self._pending_transfers:
                self._pending_transfers[channel.id].cancel()
                del self._pending_transfers[channel.id]

            # Clean up all tracking for this channel
            self._member_join_times.pop(channel.id, None)
            self._message_counts.pop(channel.id, None)
            self._panel_locks.pop(channel.id, None)

            db.delete_temp_channel(channel.id)
            try:
                await channel.delete(reason="Empty")
                log.tree("Channel Auto-Deleted", [
                    ("Channel", channel_name),
                    ("Owner ID", str(owner_id)),
                ], emoji="🗑️")

                # Schedule reorder (debounced, non-blocking)
                self.schedule_reorder(guild)

            except discord.HTTPException as e:
                log.error_tree("Empty Channel Delete Failed", e, [
                    ("Channel", channel_name),
                ])

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
            log.error_tree("Transfer Error", e, [
                ("Channel", channel.name if channel else "Unknown"),
            ])
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

            # Grant new owner permissions (boosters get manage_channels for renaming)
            await set_owner_permissions(channel, new_owner)

            # Update DB ownership
            db.transfer_ownership(channel.id, new_owner.id)

            # Generate channel name for new owner (keeps same position)
            base_name, name_source = generate_base_name(new_owner)
            position = self._get_channel_position(channel)
            channel_name = build_full_name(position, base_name)

            await channel.edit(name=channel_name)
            db.update_temp_channel(channel.id, name=channel_name, base_name=base_name)

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
                            log.error_tree("Blocked User Kick Failed", e, [
                                ("Channel", channel.name),
                                ("User", f"{blocked_user.name} ({blocked_user.display_name})"),
                                ("ID", str(blocked_user.id)),
                            ])
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
                    log.error_tree("Notification Delete Failed", e, [
                        ("Channel", channel.name),
                    ])
            except discord.HTTPException as e:
                log.error_tree("Transfer Notification Failed", e, [
                    ("Channel", channel.name),
                    ("New Owner", str(new_owner)),
                ])

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
            log.error_tree("Auto-Transfer Failed", e, [
                ("Channel", channel.name),
                ("From", str(old_owner)),
                ("To", str(new_owner)),
            ])
        except Exception as e:
            log.error_tree("Auto-Transfer Error", e, [
                ("Channel", channel.name),
            ])
