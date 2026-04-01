"""
SyriaBot - TempVoice Lifecycle
===============================

Channel creation, deletion, ownership transfer, and reordering logic.

Extracted from service.py to keep the main service class focused on
event handling and panel management.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import discord

from src.core.config import config
from src.core.constants import (
    TEMPVOICE_JOIN_COOLDOWN,
    TEMPVOICE_OWNER_LEAVE_TRANSFER_DELAY,
    TEMPVOICE_REORDER_DEBOUNCE_DELAY,
)
from src.core.colors import EMOJI_TRANSFER
from src.core.logger import logger
from src.services.database import db
from src.utils.async_utils import create_safe_task
from .permissions import sync_channel_permissions
from .utils import (
    generate_base_name,
    build_full_name,
    extract_base_name,
    get_channel_position,
    get_owner_overwrite,
    has_vc_mod_role,
    get_blocked_overwrite,
    get_trusted_overwrite,
    get_locked_overwrite,
    get_unlocked_overwrite,
    get_vc_mod_overwrite,
)

if TYPE_CHECKING:
    from .service import TempVoiceService

# Aliases
JOIN_COOLDOWN = TEMPVOICE_JOIN_COOLDOWN
OWNER_LEAVE_TRANSFER_DELAY = TEMPVOICE_OWNER_LEAVE_TRANSFER_DELAY
REORDER_DEBOUNCE_DELAY = TEMPVOICE_REORDER_DEBOUNCE_DELAY

# Per-user creation concurrency control
_create_semaphore = asyncio.Semaphore(3)  # max 3 concurrent creations
_creating_users: set[int] = set()  # user IDs currently in-flight


async def create_temp_channel(svc: TempVoiceService, member: discord.Member) -> None:
    """Create a new temp voice channel for a member.

    Uses a global semaphore (max 3 concurrent) plus a per-user guard
    so the same user can't trigger two creations simultaneously.
    """
    user_id = member.id

    # Per-user guard: reject if this user is already creating
    if user_id in _creating_users:
        logger.tree("Create Skipped (Duplicate)", [
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(user_id)),
            ("Reason", "Creation already in progress for this user"),
        ], emoji="⏭️")
        return

    _creating_users.add(user_id)
    try:
        # Wait for a slot in the global semaphore (max 3 concurrent)
        try:
            await asyncio.wait_for(_create_semaphore.acquire(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.tree("Create Semaphore Timeout", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(user_id)),
                ("Action", "Giving up after 15s wait"),
            ], emoji="⚠️")
            return

        try:
            logger.tree("Create Slot Acquired", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(user_id)),
            ], emoji="🔓")
            await _create_temp_channel_inner(svc, member)
        finally:
            _create_semaphore.release()
    finally:
        _creating_users.discard(user_id)


async def _create_temp_channel_inner(svc: TempVoiceService, member: discord.Member) -> None:
    """Inner method for channel creation (called within semaphore slot)."""
    guild = member.guild
    member_id = member.id

    logger.tree("Create Inner Started", [
        ("User", f"{member.name} ({member.display_name})"),
        ("ID", str(member.id)),
        ("Guild", guild.name),
    ], emoji="🔧")

    # Re-fetch member to get current voice state (cache may be stale after waiting)
    try:
        member = guild.get_member(member_id)
        if not member:
            logger.tree("Create Skipped", [
                ("ID", str(member_id)),
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

        logger.tree("Member Refetched", [
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
            ("Channel", channel_name),
            ("State", state_str),
        ], emoji="🔍")
    except Exception as e:
        logger.error_tree("Create Member Fetch Failed", e, [
            ("ID", str(member_id)),
        ])
        return

    # Check if user is still in creator channel (they may have left while waiting)
    if not member.voice or not member.voice.channel:
        logger.tree("Create Skipped", [
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
            ("Reason", "User no longer in any voice channel"),
        ], emoji="⏭️")
        return

    if member.voice.channel.id != config.VC_CREATOR_CHANNEL_ID:
        logger.tree("Create Skipped", [
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
            ("Current Channel", member.voice.channel.name),
            ("Reason", "User moved to different channel while waiting"),
        ], emoji="⏭️")
        return

    # Check cooldown to prevent spam
    now = time.time()
    last_join = svc._join_cooldowns.get(member.id, 0)
    if now - last_join < JOIN_COOLDOWN:
        remaining = JOIN_COOLDOWN - (now - last_join)
        logger.tree("Join Cooldown", [
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
            ("Remaining", f"{remaining:.1f}s"),
        ], emoji="⏳")
        # Disconnect them from creator channel
        try:
            await member.move_to(None)
        except discord.HTTPException as e:
            logger.error_tree("Cooldown Disconnect Failed", e, [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])
        return

    # Update cooldown timestamp
    svc._join_cooldowns[member.id] = now

    # Cleanup old cooldown entries (older than 1 minute) to prevent memory leak
    cutoff = now - 60
    svc._join_cooldowns = {
        uid: ts for uid, ts in svc._join_cooldowns.items()
        if ts > cutoff
    }

    # Check if user already owns a channel
    existing = db.get_owner_channel(member.id, guild.id)
    if existing:
        channel = guild.get_channel(existing)
        if channel:
            # Cancel pending transfers and claims for this channel
            task = svc._pending_transfers.pop(channel.id, None)
            if task:
                task.cancel()
            svc._pending_claims.discard(channel.id)

            # Transfer ownership to someone else in the channel, or delete if empty
            existing_owners = {ch["owner_id"] for ch in db.get_all_temp_channels(guild.id)}
            other_members = [
                m for m in channel.members
                if m.id != member.id and not m.bot
                and m.id not in existing_owners
            ]
            if other_members:
                # Transfer to first eligible member
                new_owner = other_members[0]
                try:
                    channel_name = await svc._transfer_ownership(channel, member.id, new_owner)
                    await svc._update_panel(channel)

                    logger.tree("Auto-Transfer", [
                        ("Channel", channel_name),
                        ("From", f"{member.name} ({member.display_name})"),
                        ("From ID", str(member.id)),
                        ("To", f"{new_owner.name} ({new_owner.display_name})"),
                        ("To ID", str(new_owner.id)),
                    ], emoji="🔄")
                except discord.HTTPException as e:
                    logger.error_tree("Auto-Transfer Failed", e, [
                        ("Channel", channel.name),
                        ("From", f"{member.name} ({member.display_name})"),
                        ("From ID", str(member.id)),
                        ("To", f"{new_owner.name} ({new_owner.display_name})"),
                        ("To ID", str(new_owner.id)),
                    ])
            else:
                # Channel is empty, delete it
                try:
                    await channel.delete(reason="Owner left, no other members")
                    db.delete_temp_channel(channel.id)
                    logger.tree("Channel Auto-Deleted", [
                        ("Channel", channel.name),
                        ("Reason", "Owner creating new VC"),
                    ], emoji="🗑️")
                except discord.HTTPException as e:
                    logger.error_tree("Auto-Delete Failed", e, [
                        ("Channel", channel.name),
                        ("Owner", f"{member.name} ({member.display_name})"),
                        ("Owner ID", str(member.id)),
                    ])
        else:
            db.delete_temp_channel(existing)
            logger.tree("Orphan DB Entry Cleaned", [
                ("Channel ID", str(existing)),
                ("Owner", f"{member.name} ({member.display_name})"),
                ("Owner ID", str(member.id)),
            ], emoji="🧹")

    # Clean up stale trusted/blocked users in background (don't block channel creation)
    guild_member_ids = {m.id for m in guild.members}

    async def _stale_cleanup() -> None:
        stale_removed = db.cleanup_stale_users(member.id, guild_member_ids)
        if stale_removed > 0:
            logger.tree("Stale User Cleanup", [
                ("Owner", f"{member.name} ({member.display_name})"),
                ("Owner ID", str(member.id)),
                ("Entries Removed", str(stale_removed)),
                ("Reason", "Users left server"),
            ], emoji="🧹")

    create_safe_task(_stale_cleanup(), "TempVoice Stale Cleanup")

    # Get user settings for default limit
    settings = db.get_user_settings(member.id)
    default_limit = settings.get("default_limit", 0) if settings else 0

    # Generate channel name with position-based numbering
    base_name, name_source = generate_base_name(member)
    position = get_next_position(guild)
    channel_name = build_full_name(position, base_name)

    logger.tree("Creating Channel", [
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
            logger.tree("Category Not Found", [
                ("Category ID", str(config.VC_CATEGORY_ID)),
                ("Action", "Creating without category"),
            ], emoji="⚠️")

    try:
        # Build all overwrites upfront (single API call instead of multiple)
        is_developer = member.id == config.OWNER_ID
        auto_lock = is_developer or member.id in config.VC_AUTO_LOCK_USERS
        overwrites = {
            # Auto-lock users get locked by default, everyone else unlocked
            guild.default_role: get_locked_overwrite() if auto_lock else get_unlocked_overwrite(),
            # Owner permissions (no manage_channels - use bot's rename button)
            member: get_owner_overwrite(),
        }

        # Specific mod roles get full access (except developer's channels)
        if config.VC_MOD_ROLES and member.id != config.OWNER_ID:
            for role_id in config.VC_MOD_ROLES:
                mod_role = guild.get_role(role_id)
                if mod_role:
                    overwrites[mod_role] = get_vc_mod_overwrite()

        # Pre-build blocked user overwrites (use Object for uncached members)
        blocked_count = 0
        for blocked_id in db.get_blocked_list(member.id):
            blocked_member = guild.get_member(blocked_id)
            # Check if user has VC mod role (only if cached)
            if blocked_member and has_vc_mod_role(blocked_member) and member.id != config.OWNER_ID:
                logger.tree("Block Skipped", [
                    ("User", f"{blocked_member.name} ({blocked_member.display_name})"),
                    ("ID", str(blocked_id)),
                    ("Reason", "Has VC mod role"),
                ], emoji="⚠️")
                continue
            # Use Object so block works even if member isn't cached
            overwrites[blocked_member or discord.Object(id=blocked_id)] = get_blocked_overwrite()
            blocked_count += 1

        # Pre-build trusted user overwrites (use Object for uncached members)
        trusted_count = 0
        for trusted_id in db.get_trusted_list(member.id):
            trusted_member = guild.get_member(trusted_id)
            overwrites[trusted_member or discord.Object(id=trusted_id)] = get_trusted_overwrite()
            trusted_count += 1

        # Create channel with ALL permissions in one API call
        channel = await guild.create_voice_channel(
            name=channel_name,
            category=category,
            user_limit=default_limit,
            overwrites=overwrites,
            reason=f"TempVoice for {member}"
        )

        # Store in database
        db.create_temp_channel(channel.id, member.id, guild.id, channel_name)
        db.update_temp_channel(channel.id, is_locked=1 if auto_lock else 0, base_name=base_name)

        # Mark panel as pending so _update_panel skips recovery
        # (moving user triggers _grant_text_access -> _update_panel)
        svc._pending_panels.add(channel.id)

        # Re-check voice state right before move (user may have disconnected during channel creation)
        if not member.voice or not member.voice.channel:
            logger.tree("Create Skipped", [
                ("Channel", channel_name),
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Reason", "User disconnected during channel creation"),
            ], emoji="⏭️")
            svc._pending_panels.discard(channel.id)
            db.delete_temp_channel(channel.id)
            await channel.delete(reason="User disconnected before move")
            return

        # Move user FIRST for instant response
        try:
            await member.move_to(channel)
        except discord.HTTPException as e:
            logger.error_tree("Move User Failed", e, [
                ("Channel", channel_name),
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])
            svc._pending_panels.discard(channel.id)
            db.delete_temp_channel(channel.id)
            await channel.delete(reason="Failed to move user")
            return

        # Send guide images + control panel after user is already in the channel
        try:
            await svc._send_channel_interface(channel, member)
        except Exception as e:
            logger.error_tree("Panel Send Failed", e, [
                ("Channel", channel_name),
            ])
        finally:
            svc._pending_panels.discard(channel.id)

        logger.tree("Channel Created", [
            ("Channel", channel_name),
            ("Owner", f"{member.name} ({member.display_name})"),
            ("Owner ID", str(member.id)),
            ("Allowed Applied", str(trusted_count)),
            ("Blocked Applied", str(blocked_count)),
        ], emoji="🔊")

    except discord.HTTPException as e:
        logger.error_tree("Channel Creation Failed", e, [
            ("Owner", f"{member.name} ({member.display_name})"),
            ("Owner ID", str(member.id)),
        ])
    except Exception as e:
        logger.error_tree("Channel Creation Error", e, [
            ("Owner", f"{member.name} ({member.display_name})"),
            ("Owner ID", str(member.id)),
        ])


async def check_empty_channel(svc: TempVoiceService, channel: discord.VoiceChannel) -> None:
    """Check if channel is empty and should be deleted."""
    if not db.is_temp_channel(channel.id):
        return

    if len(channel.members) == 0:
        channel_name = channel.name
        channel_info = db.get_temp_channel(channel.id)
        owner_id = channel_info["owner_id"] if channel_info else "Unknown"
        guild = channel.guild  # Save before deletion

        # Cancel any pending transfer and claims
        if channel.id in svc._pending_transfers:
            svc._pending_transfers[channel.id].cancel()
            del svc._pending_transfers[channel.id]
        svc._pending_claims.discard(channel.id)

        # Clean up all tracking for this channel
        cleanup_channel_cache(svc, channel.id)

        try:
            await channel.delete(reason="Empty")
            # Delete DB record after Discord delete succeeds
            db.delete_temp_channel(channel.id)
            logger.tree("Channel Auto-Deleted", [
                ("Channel", channel_name),
                ("Owner ID", str(owner_id)),
            ], emoji="🗑️")

            # Schedule reorder (debounced, non-blocking)
            schedule_reorder(svc, guild)

        except discord.NotFound:
            # Already deleted by another path - clean up DB
            db.delete_temp_channel(channel.id)
        except discord.HTTPException as e:
            logger.error_tree("Empty Channel Delete Failed", e, [
                ("Channel", channel_name),
            ])


async def schedule_owner_transfer(svc: TempVoiceService, channel: discord.VoiceChannel, old_owner: discord.Member) -> None:
    """Schedule a delayed owner transfer when owner leaves the channel."""
    # Cancel any existing pending transfer for this channel
    if channel.id in svc._pending_transfers:
        svc._pending_transfers[channel.id].cancel()

    # Get remaining members (non-bot)
    remaining = [m for m in channel.members if not m.bot]
    if not remaining:
        # No one left to transfer to - check empty will handle deletion
        await check_empty_channel(svc, channel)
        return

    logger.tree("Owner Left Channel", [
        ("Channel", channel.name),
        ("Owner", str(old_owner)),
        ("Remaining Members", str(len(remaining))),
        ("Transfer Delay", f"{OWNER_LEAVE_TRANSFER_DELAY}s"),
    ], emoji="⏳")

    # Schedule the transfer
    task = create_safe_task(_execute_owner_transfer(svc, channel, old_owner), "TempVoice Owner Transfer")
    svc._pending_transfers[channel.id] = task


async def _execute_owner_transfer(svc: TempVoiceService, channel: discord.VoiceChannel, old_owner: discord.Member) -> None:
    """Execute the delayed owner transfer after waiting."""
    try:
        # Wait before transferring
        await asyncio.sleep(OWNER_LEAVE_TRANSFER_DELAY)

        # Re-fetch channel to ensure it still exists
        channel = old_owner.guild.get_channel(channel.id)
        if not channel:
            logger.tree("Transfer Cancelled", [
                ("Reason", "Channel no longer exists"),
            ], emoji="❌")
            return

        # Check if channel is still a temp channel
        channel_info = db.get_temp_channel(channel.id)
        if not channel_info:
            logger.tree("Transfer Cancelled", [
                ("Channel", channel.name),
                ("Reason", "No longer a temp channel"),
            ], emoji="❌")
            return

        # Check if owner is back
        if any(m.id == channel_info["owner_id"] for m in channel.members):
            logger.tree("Transfer Cancelled", [
                ("Channel", channel.name),
                ("Reason", "Owner is back in channel"),
            ], emoji="↩️")
            return

        # Get remaining members (non-bot)
        remaining = [m for m in channel.members if not m.bot]
        if not remaining:
            # No one left - delete channel
            await check_empty_channel(svc, channel)
            return

        # Find the longest-in-channel member who doesn't already own a channel
        join_times = svc._member_join_times.get(channel.id, {})
        existing_owners = {ch["owner_id"] for ch in db.get_all_temp_channels(channel.guild.id)}
        eligible = [m for m in remaining if m.id not in existing_owners]
        if not eligible:
            # Everyone already owns a channel - just pick longest anyway
            eligible = remaining

        if join_times:
            # Sort by join time (oldest first)
            sorted_members = sorted(
                [(m, join_times.get(m.id, float('inf'))) for m in eligible],
                key=lambda x: x[1]
            )
            new_owner = sorted_members[0][0]
        else:
            # Fallback: first eligible member
            new_owner = eligible[0]

        # Execute the transfer
        await apply_owner_transfer(svc, channel, old_owner, new_owner)

    except asyncio.CancelledError:
        logger.tree("Transfer Cancelled", [
            ("Channel", channel.name if channel else "Unknown"),
            ("Reason", "Task cancelled (owner likely rejoined)"),
        ], emoji="↩️")
    except Exception as e:
        logger.error_tree("Transfer Error", e, [
            ("Channel", getattr(channel, 'name', 'Unknown')),
        ])
    finally:
        # Clean up the pending transfer entry
        channel_id = getattr(channel, 'id', None)
        if channel_id:
            svc._pending_transfers.pop(channel_id, None)


async def apply_owner_transfer(
    svc: TempVoiceService,
    channel: discord.VoiceChannel,
    old_owner: discord.Member,
    new_owner: discord.Member,
) -> None:
    """Apply the ownership transfer to a new owner with their settings."""
    try:
        channel_name = await svc._transfer_ownership(channel, old_owner.id, new_owner)

        # Clear all messages in the VC chat (fresh start for new owner)
        try:
            await channel.purge(limit=500, reason="Ownership transfer - clearing chat")
            logger.tree("VC Chat Cleared", [
                ("Channel", channel.name),
                ("Reason", "Ownership transfer"),
            ], emoji="🧹")
        except discord.HTTPException as e:
            logger.error_tree("VC Chat Clear Failed", e, [
                ("Channel", channel.name),
            ])

        # Send fresh control panel for the new owner
        try:
            await svc._send_channel_interface(channel, new_owner)
        except discord.HTTPException as e:
            logger.error_tree("New Panel Send Failed", e, [
                ("Channel", channel.name),
                ("New Owner", str(new_owner)),
            ])

        # Notify new owner about the transfer
        try:
            await channel.send(
                f"{EMOJI_TRANSFER} **Ownership Transferred**\n"
                f"{new_owner.mention} you are now the owner of this channel.\n"
                f"*The previous owner left and you were here the longest.*"
            )
        except discord.HTTPException as e:
            logger.error_tree("Transfer Notification Failed", e, [
                ("Channel", channel.name),
                ("New Owner", str(new_owner)),
            ])

        logger.tree("Auto-Transfer Complete", [
            ("Channel", channel_name),
            ("From", str(old_owner)),
            ("To", str(new_owner)),
        ], emoji="🔄")

    except discord.NotFound:
        svc._handle_channel_gone(channel.id, channel.name)
    except discord.HTTPException as e:
        logger.error_tree("Auto-Transfer Failed", e, [
            ("Channel", channel.name),
            ("From", str(old_owner)),
            ("To", str(new_owner)),
        ])
    except Exception as e:
        logger.error_tree("Auto-Transfer Error", e, [
            ("Channel", channel.name),
        ])


async def cleanup_empty_channels(svc: TempVoiceService) -> None:
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

        channel = svc.bot.get_channel(channel_id)

        # Channel doesn't exist in Discord - clean up DB
        if not channel:
            db.delete_temp_channel(channel_id)
            cleanup_channel_cache(svc, channel_id)
            cleaned += 1
            if guild_id:
                guilds_affected.add(guild_id)
            logger.tree("Orphan Channel Cleaned", [
                ("Channel ID", str(channel_id)),
                ("Reason", "Channel not in Discord"),
            ], emoji="🧹")
            continue

        # Channel exists but is empty - delete it
        # Wrap in try-except to handle stale channel references
        try:
            member_count = len(channel.members)
        except (AttributeError, TypeError):
            # Channel reference is stale - clean up DB
            db.delete_temp_channel(channel_id)
            cleanup_channel_cache(svc, channel_id)
            cleaned += 1
            logger.tree("Stale Channel Cleaned", [
                ("Channel ID", str(channel_id)),
                ("Reason", "Stale reference"),
            ], emoji="🧹")
            continue

        if member_count == 0:
            try:
                channel_name = channel.name
                guild_id_for_reorder = channel.guild.id
                await channel.delete(reason="Empty channel cleanup")
                # Delete DB record after Discord delete succeeds
                db.delete_temp_channel(channel_id)
                cleanup_channel_cache(svc, channel_id)
                cleaned += 1
                guilds_affected.add(guild_id_for_reorder)
                logger.tree("Empty Channel Cleaned", [
                    ("Channel", channel_name),
                    ("Reason", "Periodic cleanup"),
                ], emoji="🧹")
            except discord.NotFound:
                db.delete_temp_channel(channel_id)
                cleanup_channel_cache(svc, channel_id)
                cleaned += 1
            except discord.HTTPException as e:
                logger.error_tree("Empty Channel Delete Failed", e, [
                    ("Channel ID", str(channel_id)),
                ])

    if cleaned > 0:
        logger.tree("Periodic Cleanup Complete", [
            ("Channels Removed", str(cleaned)),
        ], emoji="🧹")

        # Schedule reorder for affected guilds (debounced)
        for guild_id in guilds_affected:
            guild = svc.bot.get_guild(guild_id)
            if guild:
                schedule_reorder(svc, guild)


async def cleanup_orphaned_channels(svc: TempVoiceService) -> None:
    """Clean up temp channels that no longer exist."""
    channels = db.get_all_temp_channels()
    cleaned = 0

    for channel_data in channels:
        channel_id = channel_data["channel_id"]
        channel = svc.bot.get_channel(channel_id)
        if not channel:
            db.delete_temp_channel(channel_id)
            cleanup_channel_cache(svc, channel_id)
            cleaned += 1

    if cleaned > 0:
        logger.tree("Orphan Cleanup", [
            ("Channels Removed", str(cleaned)),
            ("Reason", "Channel no longer exists"),
        ], emoji="🧹")


def cleanup_channel_cache(svc: TempVoiceService, channel_id: int) -> None:
    """Remove all cached state for a channel."""
    from .permissions import cleanup_channel_lock
    svc._panel_locks.pop(channel_id, None)
    svc._member_join_times.pop(channel_id, None)
    svc._message_counts.pop(channel_id, None)
    cleanup_channel_lock(channel_id)
    # Clean up kick cooldowns for this channel
    stale_keys = [k for k in svc._kick_cooldowns if k[0] == channel_id]
    for k in stale_keys:
        del svc._kick_cooldowns[k]


def schedule_reorder(svc: TempVoiceService, guild: discord.Guild) -> None:
    """
    Schedule a debounced channel reorder for a guild.

    If multiple deletions happen quickly (bulk cleanup), this ensures
    we only reorder once after all deletions are done.

    Non-blocking - fires and forgets the background task.
    """
    guild_id = guild.id

    # Cancel any existing pending reorder for this guild (race-safe)
    existing_task = svc._pending_reorders.pop(guild_id, None)
    if existing_task:
        existing_task.cancel()
        logger.tree("Reorder Rescheduled", [
            ("Guild", guild.name),
            ("Reason", "New deletion during debounce"),
        ], emoji="🔄")

    # Schedule new reorder after debounce delay
    task = create_safe_task(_debounced_reorder(svc, guild), "TempVoice Reorder")
    svc._pending_reorders[guild_id] = task

    if not existing_task:
        logger.tree("Reorder Scheduled", [
            ("Guild", guild.name),
            ("Delay", f"{REORDER_DEBOUNCE_DELAY}s"),
        ], emoji="📋")


async def _debounced_reorder(svc: TempVoiceService, guild: discord.Guild) -> None:
    """Wait for debounce delay, then execute reorder."""
    try:
        await asyncio.sleep(REORDER_DEBOUNCE_DELAY)
        await _reorder_channels(svc, guild)
    except asyncio.CancelledError:
        # Another reorder was scheduled, this one is cancelled (already logged in schedule_reorder)
        pass
    except Exception as e:
        logger.error_tree("Debounced Reorder Error", e, [
            ("Guild", guild.name),
        ])
    finally:
        # Clean up the pending task reference
        svc._pending_reorders.pop(guild.id, None)


async def _reorder_channels(svc: TempVoiceService, guild: discord.Guild) -> None:
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

    logger.tree("Reordering Channels", [
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
                logger.tree("Channel Renumbered", [
                    ("From", old_name),
                    ("To", new_name),
                    ("Position", str(position)),
                ], emoji="🔢")

            # Discord rate limits channel renames to 2 per 10 min per channel
            await asyncio.sleep(3)

        except discord.HTTPException as e:
            logger.error_tree("Reorder Rename Failed", e, [
                ("Channel", channel.name),
                ("Target", new_name),
            ])
        except Exception as e:
            logger.error_tree("Reorder Error", e, [
                ("Channel", channel.name),
            ])

    # Summary log for bulk renames
    if len(channels_to_rename) > 3:
        logger.tree("Reorder Complete", [
            ("Renamed", f"{renamed_count}/{len(channels_to_rename)}"),
            ("Category", category.name),
        ], emoji="✅")


def get_next_position(guild: discord.Guild) -> int:
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


async def rename_for_new_owner(svc: TempVoiceService, channel: discord.VoiceChannel, new_owner: discord.Member) -> str:
    """Rename a channel to the new owner's default name, keeping its position."""
    base_name, _ = generate_base_name(new_owner)
    position = get_channel_position(channel)
    channel_name = build_full_name(position, base_name)
    await channel.edit(name=channel_name)
    db.update_temp_channel(channel.id, name=channel_name, base_name=base_name)
    return channel_name
