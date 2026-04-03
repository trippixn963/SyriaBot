"""
SyriaBot - TempVoice Service
============================

Temporary voice channel system with ownership and control panel.

Features:
    - Join-to-create voice channels
    - Owner controls (lock, limit, rename, transfer)
    - Trust/block user management
    - Auto-cleanup of empty channels
    - Sticky control panel messages

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import time
from typing import TYPE_CHECKING

import discord

from src.core.config import config
from src.core.colors import EMOJI_TRANSFER
from src.core.constants import (
    TEMPVOICE_JOIN_COOLDOWN,
    TEMPVOICE_OWNER_LEAVE_TRANSFER_DELAY,
    TEMPVOICE_STICKY_PANEL_THRESHOLD,
    TEMPVOICE_REORDER_DEBOUNCE_DELAY,
)
from src.core.logger import logger
from src.services.database import db
from src.utils.async_utils import create_safe_task
from .lifecycle import (
    create_temp_channel as _lifecycle_create_temp_channel,
    check_empty_channel as _lifecycle_check_empty_channel,
    schedule_owner_transfer as _lifecycle_schedule_owner_transfer,
    apply_owner_transfer as _lifecycle_apply_owner_transfer,
    cleanup_empty_channels as _lifecycle_cleanup_empty_channels,
    cleanup_orphaned_channels as _lifecycle_cleanup_orphaned_channels,
    cleanup_channel_cache as _lifecycle_cleanup_channel_cache,
    schedule_reorder as _lifecycle_schedule_reorder,
    rename_for_new_owner as _lifecycle_rename_for_new_owner,
    get_next_position as _lifecycle_get_next_position,
)
from .utils import (
    generate_base_name,
    build_full_name,
    extract_base_name,
    is_booster,
    has_vc_mod_role,
    get_channel_position,
    get_owner_overwrite,
    set_owner_permissions,
    get_trusted_overwrite,
    get_blocked_overwrite,
    get_locked_overwrite,
    get_unlocked_overwrite,
    get_vc_mod_overwrite,
)
from .views import TempVoiceControlPanel
from .panel import (
    build_panel_embed,
    build_panel_view,
    send_guide_images,
    send_channel_interface,
    update_panel,
    update_voice_status,
    resend_sticky_panel,
    resend_interface_panel,
)

if TYPE_CHECKING:
    from src.bot import SyriaBot

KICK_REJOIN_COOLDOWN = 300  # 5 minutes before kicked user can rejoin

# Aliases for backwards compatibility
JOIN_COOLDOWN = TEMPVOICE_JOIN_COOLDOWN
OWNER_LEAVE_TRANSFER_DELAY = TEMPVOICE_OWNER_LEAVE_TRANSFER_DELAY
STICKY_PANEL_MESSAGE_THRESHOLD = TEMPVOICE_STICKY_PANEL_THRESHOLD
REORDER_DEBOUNCE_DELAY = TEMPVOICE_REORDER_DEBOUNCE_DELAY

# CSS-rendered guide images moved to panel.py


class TempVoiceService:
    """
    Service for managing temporary voice channels.

    DESIGN:
        Users join a creator channel to spawn their own temp VC.
        The creator becomes the owner with full control.
        Channels auto-delete when empty after cleanup interval.
        Control panel allows lock/unlock, user limit, rename, etc.
    """

    def __init__(self, bot: "SyriaBot") -> None:
        """
        Initialize the TempVoice service.

        Sets up tracking for:
        - Control panel view (persistent buttons)
        - Join cooldowns (prevents spam creation)
        - Member join times (for ownership transfer)
        - Pending transfers (when owner leaves)
        - Message counts (for sticky panel refresh)

        Args:
            bot: Main bot instance for Discord API access.
        """
        self.bot = bot
        self.control_panel = TempVoiceControlPanel(self)
        self._cleanup_task: asyncio.Task = None
        self._join_cooldowns: dict[int, float] = {}  # user_id -> last join timestamp
        self._kick_cooldowns: dict[tuple[int, int], float] = {}  # (channel_id, user_id) -> kick timestamp
        self._member_join_times: dict[int, dict[int, float]] = {}  # channel_id -> {user_id: join_time}
        self._pending_transfers: dict[int, asyncio.Task] = {}  # channel_id -> pending transfer task
        self._message_counts: dict[int, int] = {}  # channel_id -> message count since last panel
        self._pending_reorders: dict[int, asyncio.Task] = {}  # guild_id -> pending reorder task (debounced)
        self._panel_locks: dict[int, asyncio.Lock] = {}  # channel_id -> lock for panel updates
        self._pending_claims: set[int] = set()  # channel_ids with active claim requests
        self._pending_panels: set[int] = set()  # channel_ids where panel creation is in progress

    def _handle_channel_gone(self, channel_id: int, channel_name: str = "Unknown") -> None:
        """Clean up all state for a channel that no longer exists on Discord."""
        db.delete_temp_channel(channel_id)
        self._cleanup_channel_cache(channel_id)
        logger.tree("Stale Channel Cleaned", [
            ("Channel", channel_name),
            ("ID", str(channel_id)),
        ], emoji="🗑️")

    async def setup(self) -> None:
        """
        Initialize and start the TempVoice service.

        Validates configuration, registers the control panel view,
        cleans up orphaned channels from previous runs, and starts
        the periodic cleanup task.
        """
        # Validate config
        warnings = []
        if not config.VC_CREATOR_CHANNEL_ID:
            warnings.append("VC_CREATOR_CHANNEL_ID not set - join-to-create disabled")
        if not config.VC_CATEGORY_ID:
            warnings.append("VC_CATEGORY_ID not set - VCs will be created without category")
        if not config.VC_MOD_ROLES:
            warnings.append("VC_MOD_ROLES not set - no roles can enter locked VCs")

        if warnings:
            logger.tree("TempVoice Config Warnings", [
                (f"⚠️ {i+1}", w) for i, w in enumerate(warnings)
            ], emoji="⚠️")

        self.bot.add_view(self.control_panel)
        await _lifecycle_cleanup_orphaned_channels(self)
        await _lifecycle_cleanup_empty_channels(self)  # Initial cleanup
        await self._strip_manage_channels()  # One-time fix for existing channels

        # Sync all channel permissions from DB (fixes drift from restarts/crashes)
        from .permissions import sync_all_channels
        await sync_all_channels(self.bot)

        # Start periodic cleanup task
        self._cleanup_task = create_safe_task(self._periodic_cleanup(), "TempVoice Cleanup")

        cleanup_mins = config.VC_CLEANUP_INTERVAL // 60
        logger.tree("TempVoice Service", [
            ("Status", "Initialized"),
            ("Creator Channel", str(config.VC_CREATOR_CHANNEL_ID) if config.VC_CREATOR_CHANNEL_ID else "Not set"),
            ("Category", str(config.VC_CATEGORY_ID) if config.VC_CATEGORY_ID else "Not set"),
            ("VC Mod Roles", str(len(config.VC_MOD_ROLES)) if config.VC_MOD_ROLES else "Not set"),
            ("Cleanup Interval", f"{cleanup_mins} minutes"),
        ], emoji="🔊")

    async def stop(self) -> None:
        """
        Stop the TempVoice service and cleanup resources.

        Cancels all background tasks (cleanup, transfers, reorders)
        and clears all tracking caches to prevent memory leaks.
        """
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

        # Clear all channel tracking caches to prevent memory leaks
        locks_count = len(self._panel_locks)
        self._join_cooldowns.clear()
        self._member_join_times.clear()
        self._message_counts.clear()
        self._panel_locks.clear()
        self._pending_panels.clear()
        self._pending_claims.clear()

        logger.tree("TempVoice Service Stopped", [
            ("Cancelled Tasks", str(len(cancelled_tasks))),
            ("Panel Locks Cleared", str(locks_count)),
        ], emoji="🔇")

    def _cleanup_channel_cache(self, channel_id: int) -> None:
        """Remove all cached state for a channel."""
        _lifecycle_cleanup_channel_cache(self, channel_id)

    async def _transfer_ownership(
        self,
        channel: discord.VoiceChannel,
        old_owner_id: int,
        new_owner: discord.Member,
    ) -> str:
        """Core transfer: DB transfer, rename, full permission sync from DB.

        Returns the new channel name.
        """
        from .permissions import sync_channel_permissions

        db.transfer_ownership(channel.id, new_owner.id)
        channel_name = await self._rename_for_new_owner(channel, new_owner)
        # Single atomic permission rebuild from new owner's DB state
        await sync_channel_permissions(channel)
        return channel_name

    async def _periodic_cleanup(self) -> None:
        """Periodically clean up empty temp channels and refresh VC statuses."""
        while True:
            await asyncio.sleep(config.VC_CLEANUP_INTERVAL)
            try:
                await _lifecycle_cleanup_empty_channels(self)
            except Exception as e:
                logger.error_tree("Periodic Cleanup Failed", e)

            # Refresh all temp VC statuses (Discord clears them periodically)
            try:
                await self._refresh_all_statuses()
            except Exception as e:
                logger.error_tree("Status Refresh Failed", e)

    async def _refresh_all_statuses(self) -> None:
        """Re-set VC status only on channels where Discord cleared it."""
        from .panel import _last_status

        channels = db.get_all_temp_channels()
        if not channels:
            return

        refreshed = 0
        for channel_data in channels:
            channel_id = channel_data["channel_id"]
            guild_id = channel_data.get("guild_id", config.GUILD_ID)
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.VoiceChannel):
                continue

            # Only refresh if Discord cleared the status (status is None/empty but we expect one)
            current_status = channel.status
            expected = _last_status.get(channel_id)
            if expected and not current_status:
                _last_status.pop(channel_id, None)
                await update_voice_status(channel)
                refreshed += 1

        if refreshed > 0:
            logger.tree("VC Statuses Refreshed", [
                ("Refreshed", str(refreshed)),
            ], emoji="🔄")

    async def _enforce_blocks(self) -> None:
        """Scan all temp channels and kick any blocked users who slipped through."""
        channels = db.get_all_temp_channels()
        kicked = 0

        for channel_data in channels:
            channel_id = channel_data["channel_id"]
            owner_id = channel_data["owner_id"]
            guild_id = channel_data.get("guild_id", config.GUILD_ID)

            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.VoiceChannel):
                continue

            blocked_ids = db.get_blocked_list(owner_id)
            if not blocked_ids:
                continue

            for member in channel.members:
                if member.id in blocked_ids:
                    try:
                        await channel.set_permissions(member, overwrite=get_blocked_overwrite())
                        await member.move_to(None)
                        kicked += 1
                        logger.tree("Blocked User Enforced", [
                            ("Channel", channel.name),
                            ("User", f"{member.name} ({member.display_name})"),
                            ("ID", str(member.id)),
                            ("Owner", str(owner_id)),
                        ], emoji="🚫")
                    except discord.HTTPException:
                        pass

        if kicked > 0:
            logger.tree("Block Enforcement Complete", [
                ("Kicked", str(kicked)),
            ], emoji="🔒")

    async def _cleanup_empty_channels(self) -> None:
        """Scan and delete empty temp channels (handles missed deletions)."""
        await _lifecycle_cleanup_empty_channels(self)

    async def _cleanup_orphaned_channels(self) -> None:
        """Clean up temp channels that no longer exist."""
        await _lifecycle_cleanup_orphaned_channels(self)

    async def _strip_manage_channels(self) -> None:
        """Strip manage_channels from all channel owners (one-time migration)."""
        channels = db.get_all_temp_channels()
        total = len(channels)
        fixed = 0
        skipped = 0
        errors = 0

        logger.tree("Permission Migration Starting", [
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
                logger.tree("Permission Fixed", [
                    ("Channel", channel.name),
                    ("Channel ID", str(channel.id)),
                    ("Owner", f"{owner.name} ({owner.display_name})"),
                    ("Owner ID", str(owner.id)),
                    ("Action", "Removed manage_channels"),
                ], emoji="🔧")
            except discord.HTTPException as e:
                errors += 1
                logger.error_tree("Permission Fix Failed", e, [
                    ("Channel", channel.name),
                    ("Channel ID", str(channel_data["channel_id"])),
                    ("Owner ID", str(channel_data["owner_id"])),
                ])

        logger.tree("Permission Migration Complete", [
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
        """Build the control panel embed. Delegates to panel module."""
        return build_panel_embed(channel, owner, is_locked)

    def _build_panel_view(self, is_locked: bool = True) -> TempVoiceControlPanel:
        """Build a fresh control panel view. Delegates to panel module."""
        return build_panel_view(self, is_locked)

    async def _send_guide_images(self, channel: discord.VoiceChannel) -> tuple[int | None, int | None]:
        """Send CSS-rendered guide images. Delegates to panel module."""
        return await send_guide_images(channel)

    async def _send_channel_interface(
        self,
        channel: discord.VoiceChannel,
        owner: discord.Member,
    ) -> discord.Message:
        """Send guide images + control panel + welcome message. Delegates to panel module."""
        return await send_channel_interface(channel, owner, self)

    def _get_panel_lock(self, channel_id: int) -> asyncio.Lock:
        """Get or create a lock for panel updates on a specific channel."""
        if channel_id not in self._panel_locks:
            self._panel_locks[channel_id] = asyncio.Lock()
        return self._panel_locks[channel_id]

    async def _update_panel(self, channel: discord.VoiceChannel) -> None:
        """Update the control panel embed and VC status. Delegates to panel module."""
        await update_panel(channel, self)
        await update_voice_status(channel)

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ) -> None:
        """Handle voice state updates."""
        # Safety check - ensure member and guild are valid
        if not member or not member.guild:
            logger.tree("Voice State Update Skipped", [
                ("Reason", "Invalid member/guild"),
            ], emoji="⚠️")
            return

        # Safety check - validate channel objects have required attributes
        before_channel = before.channel if before and before.channel and hasattr(before.channel, 'id') else None
        after_channel = after.channel if after and after.channel and hasattr(after.channel, 'id') else None

        # Determine if user actually changed channels (ignore mute/deafen/stream changes)
        left_channel = before_channel and (not after_channel or before_channel.id != after_channel.id)
        joined_channel = after_channel and (not before_channel or after_channel.id != before_channel.id)

        # User left a VC - revoke text permissions
        if left_channel and before_channel.id != config.VC_CREATOR_CHANNEL_ID:
            # Skip ignored channels (managed by other bots, e.g. Quran VC)
            if before_channel.id not in config.VC_IGNORED_CHANNELS:
                # Re-fetch channel to ensure it still exists
                channel = member.guild.get_channel(before_channel.id)
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
        if joined_channel and after_channel.id != config.VC_CREATOR_CHANNEL_ID:
            # Skip ignored channels (managed by other bots, e.g. Quran VC)
            if after_channel.id in config.VC_IGNORED_CHANNELS:
                return
            # Re-fetch channel to ensure it still exists
            channel = member.guild.get_channel(after_channel.id)
            if channel:
                # Enforce kick rejoin cooldown (skip for owner, mods, and expired entries)
                kick_key = (channel.id, member.id)
                kick_time = self._kick_cooldowns.get(kick_key)
                if kick_time:
                    elapsed = time.time() - kick_time
                    if elapsed >= KICK_REJOIN_COOLDOWN:
                        # Expired — clean up
                        del self._kick_cooldowns[kick_key]
                    else:
                        # Check if user is now the owner or has mod role — bypass cooldown
                        channel_info = db.get_temp_channel(channel.id)
                        is_owner = channel_info and channel_info["owner_id"] == member.id
                        if not is_owner and not has_vc_mod_role(member):
                            remaining = int(KICK_REJOIN_COOLDOWN - elapsed)
                            try:
                                await member.move_to(None)
                                try:
                                    await member.send(
                                        f"You were kicked from **{channel.name}** and cannot rejoin for **{remaining // 60}m {remaining % 60}s**."
                                    )
                                except discord.Forbidden:
                                    pass
                                logger.tree("Kick Cooldown Enforced", [
                                    ("User", f"{member.name} ({member.display_name})"),
                                    ("ID", str(member.id)),
                                    ("Channel", channel.name),
                                    ("Remaining", f"{remaining}s"),
                                ], emoji="⏳")
                            except discord.HTTPException:
                                pass
                            return

                await self._grant_text_access(channel, member)
                # Owner rejoined - cancel pending transfer
                channel_info = db.get_temp_channel(channel.id)
                if channel_info and channel_info["owner_id"] == member.id:
                    task = self._pending_transfers.pop(channel.id, None)
                    if task:
                        task.cancel()
                        logger.tree("Owner Rejoined", [
                            ("Channel", channel.name),
                            ("Owner", f"{member.name} ({member.display_name})"),
                            ("Owner ID", str(member.id)),
                            ("Status", "Transfer cancelled"),
                        ], emoji="↩️")

                # Check if owner's channel needs renaming (lost booster status)
                await self._check_booster_name(channel, member)

        # User joined the creator channel - create new temp VC
        if joined_channel and after_channel.id == config.VC_CREATOR_CHANNEL_ID:
            await self._create_temp_channel(member)

    async def on_message(self, message: discord.Message) -> None:
        """Handle messages in temp voice channels and interface channel for sticky panel."""
        # Ignore bot messages and DMs
        if message.author.bot or not message.guild:
            return

        channel = message.channel

        # Handle interface channel (text channel for main panel)
        if config.VC_INTERFACE_CHANNEL_ID and channel.id == config.VC_INTERFACE_CHANNEL_ID:
            # Use lock to prevent race conditions on message count
            lock = self._get_panel_lock(channel.id)
            async with lock:
                self._message_counts[channel.id] = self._message_counts.get(channel.id, 0) + 1
                if self._message_counts[channel.id] >= STICKY_PANEL_MESSAGE_THRESHOLD:
                    self._message_counts[channel.id] = 0
                    await self._resend_interface_panel(channel)
            return

        # Handle temp voice channels
        if not hasattr(channel, 'voice_states'):
            return

        if not db.is_temp_channel(channel.id):
            return

        # Use lock to prevent race conditions on message count
        lock = self._get_panel_lock(channel.id)
        should_resend = False
        async with lock:
            self._message_counts[channel.id] = self._message_counts.get(channel.id, 0) + 1
            if self._message_counts[channel.id] >= STICKY_PANEL_MESSAGE_THRESHOLD:
                self._message_counts[channel.id] = 0
                should_resend = True

        if should_resend:
            await self._resend_sticky_panel(channel)

    async def _resend_sticky_panel(self, channel: discord.VoiceChannel) -> None:
        """Delete old panel and resend as sticky message. Delegates to panel module."""
        await resend_sticky_panel(channel, self)

    async def _resend_interface_panel(self, channel: discord.TextChannel) -> None:
        """Delete old interface panel and resend as sticky. Delegates to panel module."""
        await resend_interface_panel(channel, self)

    async def _grant_text_access(self, channel: discord.VoiceChannel, member: discord.Member) -> None:
        """Grant text chat access to a member in a temp VC (includes dragged-in users)."""
        from .permissions import grant_text_access as _grant_text

        try:
            if not db.is_temp_channel(channel.id):
                return

            # Track join time for this member (for auto-transfer ordering)
            if channel.id not in self._member_join_times:
                self._member_join_times[channel.id] = {}
            if member.id not in self._member_join_times[channel.id]:
                self._member_join_times[channel.id][member.id] = time.time()

            await _grant_text(channel, member)
            await self._update_panel(channel)
        except discord.NotFound:
            self._handle_channel_gone(channel.id, channel.name)
        except Exception as e:
            logger.error_tree("Text Access Grant Error", e, [
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
            position = get_channel_position(channel)
            expected_name = build_full_name(position, expected_base)
            old_name = channel.name
            await channel.edit(name=expected_name)
            db.update_temp_channel(channel.id, name=expected_name, base_name=expected_base)

            logger.tree("Channel Renamed (Lost Booster)", [
                ("Channel", channel.name),
                ("From", old_name),
                ("To", expected_name),
                ("Owner", f"{member.name} ({member.display_name})"),
                ("Owner ID", str(member.id)),
            ], emoji="💎")

            await self._update_panel(channel)

        except discord.HTTPException as e:
            logger.error_tree("Booster Name Check Failed", e, [
                ("Channel", channel.name),
                ("Channel ID", str(channel.id)),
                ("Member", f"{member.name} ({member.display_name})"),
                ("Member ID", str(member.id)),
            ])
        except Exception as e:
            logger.error_tree("Booster Name Check Error", e, [
                ("Channel", channel.name),
                ("Channel ID", str(channel.id)),
                ("Member", f"{member.name} ({member.display_name})"),
                ("Member ID", str(member.id)),
            ])

    async def _revoke_text_access(self, channel: discord.VoiceChannel, member: discord.Member) -> None:
        """Revoke text chat access from a member who left a temp VC."""
        from .permissions import revoke_text_access as _revoke_text

        try:
            if not db.is_temp_channel(channel.id):
                return

            # Clean up join time tracking
            if channel.id in self._member_join_times:
                self._member_join_times[channel.id].pop(member.id, None)

            await _revoke_text(channel, member)
            await self._update_panel(channel)
        except discord.NotFound:
            self._handle_channel_gone(channel.id, channel.name)
        except Exception as e:
            logger.error_tree("Text Access Revoke Error", e, [
                ("Channel", channel.name),
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])

    def schedule_reorder(self, guild: discord.Guild) -> None:
        """Schedule a debounced channel reorder for a guild."""
        _lifecycle_schedule_reorder(self, guild)

    def _get_next_position(self, guild: discord.Guild) -> int:
        """Get the next position number for a new temp channel."""
        return _lifecycle_get_next_position(guild)

    async def _rename_for_new_owner(self, channel: discord.VoiceChannel, new_owner: discord.Member) -> str:
        """Rename a channel to the new owner's default name, keeping its position."""
        return await _lifecycle_rename_for_new_owner(self, channel, new_owner)

    async def _apply_owner_lists(self, channel: discord.VoiceChannel, new_owner: discord.Member) -> tuple[int, int]:
        """Clear stale overwrites and apply the new owner's trusted/blocked lists.

        Re-grants text access to members currently in the channel so they
        don't lose permissions after the overwrite wipe.

        Returns (trusted_count, blocked_count).
        """
        guild = channel.guild

        # Collect IDs of members currently in the voice channel
        current_member_ids = {m.id for m in channel.members if not m.bot}

        # Clear ALL user permission overwrites (fresh slate for new owner)
        # Only keep roles (@everyone, VC mod) and bot overwrites
        for target, _ in list(channel.overwrites.items()):
            if isinstance(target, discord.Role):
                continue
            if target.id == guild.me.id:
                continue
            await channel.set_permissions(target, overwrite=None)

        # Build blocked set for quick lookup
        blocked_ids = set(db.get_blocked_list(new_owner.id))

        # Apply blocked list (use Object for uncached members)
        blocked_count = 0
        for blocked_id in blocked_ids:
            blocked_member = guild.get_member(blocked_id)
            if blocked_member and has_vc_mod_role(blocked_member) and new_owner.id != config.OWNER_ID:
                continue
            target = blocked_member or discord.Object(id=blocked_id)
            await channel.set_permissions(target, overwrite=get_blocked_overwrite())
            if blocked_member and blocked_member.voice and blocked_member.voice.channel == channel:
                try:
                    await blocked_member.move_to(None)
                except discord.HTTPException as e:
                    logger.error_tree("Blocked User Kick Failed", e, [
                            ("Channel", channel.name),
                            ("User", f"{blocked_member.name} ({blocked_member.display_name})"),
                            ("ID", str(blocked_id)),
                        ])
                blocked_count += 1

        # Apply trusted list (use Object for uncached members)
        trusted_ids = set(db.get_trusted_list(new_owner.id))
        trusted_count = 0
        for trusted_id in trusted_ids:
            trusted_member = guild.get_member(trusted_id)
            target = trusted_member or discord.Object(id=trusted_id)
            if trusted_id in current_member_ids and trusted_member:
                # In VC — give connect + text
                await channel.set_permissions(trusted_member, overwrite=discord.PermissionOverwrite(
                    connect=True,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                ))
            else:
                # Not in VC or uncached — connect only
                await channel.set_permissions(target, overwrite=get_trusted_overwrite())
            trusted_count += 1

        # Re-grant text access to members currently in the VC (no connect — they're already in)
        handled_ids = blocked_ids | trusted_ids | {new_owner.id, guild.me.id}
        unhandled_in_vc = current_member_ids - handled_ids
        logger.tree("Apply Owner Lists — Re-granting Text", [
            ("Channel", channel.name),
            ("Current Members", str(len(current_member_ids))),
            ("Handled (skip)", str(len(handled_ids))),
            ("Re-granting To", str(len(unhandled_in_vc))),
            ("Member IDs", ", ".join(str(mid) for mid in unhandled_in_vc) if unhandled_in_vc else "None"),
        ], emoji="🔄")
        for member_id in unhandled_in_vc:
            member = guild.get_member(member_id)
            if member:
                await channel.set_permissions(member, overwrite=discord.PermissionOverwrite(
                    connect=True,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                ))
                logger.tree("Text Re-granted", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                    ("Channel", channel.name),
                ], emoji="✅")

        # Update VC mod role overwrites based on new owner
        # Developer's channels: VC mods cannot enter (matches _create_temp_channel_inner logic)
        # Regular channels: VC mods get full moderation access
        if config.VC_MOD_ROLES:
            for role_id in config.VC_MOD_ROLES:
                mod_role = guild.get_role(role_id)
                if not mod_role:
                    continue
                if new_owner.id == config.OWNER_ID:
                    await channel.set_permissions(mod_role, overwrite=None)
                else:
                    await channel.set_permissions(mod_role, overwrite=get_vc_mod_overwrite())

        return trusted_count, blocked_count

    async def _create_temp_channel(self, member: discord.Member) -> None:
        """Create a new temp voice channel for a member."""
        await _lifecycle_create_temp_channel(self, member)

    async def _check_empty_channel(self, channel: discord.VoiceChannel) -> None:
        """Check if channel is empty and should be deleted."""
        await _lifecycle_check_empty_channel(self, channel)

    async def _schedule_owner_transfer(self, channel: discord.VoiceChannel, old_owner: discord.Member) -> None:
        """Schedule a delayed owner transfer when owner leaves the channel."""
        await _lifecycle_schedule_owner_transfer(self, channel, old_owner)

    async def _apply_owner_transfer(
        self,
        channel: discord.VoiceChannel,
        old_owner: discord.Member,
        new_owner: discord.Member
    ) -> None:
        """Apply the ownership transfer to a new owner with their settings."""
        await _lifecycle_apply_owner_transfer(self, channel, old_owner, new_owner)
