"""
SyriaBot - TempVoice Permission Engine
=======================================

Single source of truth for channel permissions.
One function rebuilds ALL Discord overwrites from DB state atomically.

Every mutating action (block, trust, lock, transfer) updates DB first,
then calls sync_channel_permissions() to apply. No other code should
call channel.set_permissions() directly for temp channels.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from typing import Dict, Optional, Set, Union

import discord

from src.core.config import config
from src.core.logger import logger
from src.services.database import db
from .utils import (
    get_owner_overwrite,
    get_trusted_overwrite,
    get_blocked_overwrite,
    get_locked_overwrite,
    get_unlocked_overwrite,
    get_vc_mod_overwrite,
    has_vc_mod_role,
)


OverwriteTarget = Union[discord.Role, discord.Member, discord.Object]
OverwriteDict = Dict[OverwriteTarget, discord.PermissionOverwrite]

# Per-channel locks — prevents concurrent permission mutations on the same channel
_channel_locks: Dict[int, asyncio.Lock] = {}


def get_channel_lock(channel_id: int) -> asyncio.Lock:
    """Get or create a lock for a specific channel."""
    if channel_id not in _channel_locks:
        _channel_locks[channel_id] = asyncio.Lock()
    return _channel_locks[channel_id]


def cleanup_channel_lock(channel_id: int) -> None:
    """Remove lock for a deleted channel."""
    _channel_locks.pop(channel_id, None)


def compute_overwrites(
    guild: discord.Guild,
    channel_id: int,
    current_member_ids: Optional[Set[int]] = None,
) -> Optional[OverwriteDict]:
    """
    Compute the complete set of permission overwrites for a temp channel from DB state.

    Pure function — reads DB, returns a dict. No Discord API calls.

    Args:
        guild: The guild the channel belongs to.
        channel_id: The temp channel ID.
        current_member_ids: Set of user IDs currently in the voice channel.
            If None, text access for present members is skipped.

    Returns:
        Complete overwrite dict to pass to channel.edit(overwrites=...), or None if
        the channel is not a temp channel.
    """
    channel_info = db.get_temp_channel(channel_id)
    if not channel_info:
        return None

    owner_id: int = channel_info["owner_id"]
    is_locked: bool = bool(channel_info.get("is_locked", 0))

    trusted_ids: Set[int] = set(db.get_trusted_list(owner_id))
    blocked_ids: Set[int] = set(db.get_blocked_list(owner_id))

    if current_member_ids is None:
        current_member_ids = set()

    overwrites: OverwriteDict = {}

    # 1. @everyone — locked or unlocked base permissions
    everyone_role = guild.default_role
    overwrites[everyone_role] = get_locked_overwrite() if is_locked else get_unlocked_overwrite()

    # 2. Owner — full access
    owner_member = guild.get_member(owner_id)
    owner_target: OverwriteTarget = owner_member or discord.Object(id=owner_id)
    overwrites[owner_target] = get_owner_overwrite()

    # 3. VC mod roles — moderation access (skip if owner is developer)
    if owner_id != config.OWNER_ID:
        for mod_role_id in config.VC_MOD_ROLES:
            mod_role = guild.get_role(mod_role_id)
            if mod_role:
                overwrites[mod_role] = get_vc_mod_overwrite()

    # 4. Blocked users — can see, can't join or chat
    for blocked_id in blocked_ids:
        if blocked_id == owner_id:
            continue
        blocked_member = guild.get_member(blocked_id)
        # Skip blocking VC mods (unless owner is developer)
        if blocked_member and has_vc_mod_role(blocked_member) and owner_id != config.OWNER_ID:
            continue
        target: OverwriteTarget = blocked_member or discord.Object(id=blocked_id)
        overwrites[target] = get_blocked_overwrite()

    # 5. Trusted users
    for trusted_id in trusted_ids:
        if trusted_id == owner_id or trusted_id in blocked_ids:
            continue
        trusted_member = guild.get_member(trusted_id)
        target = trusted_member or discord.Object(id=trusted_id)

        if trusted_id in current_member_ids and trusted_member:
            # In VC — connect + text
            overwrites[target] = discord.PermissionOverwrite(
                connect=True,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )
        else:
            # Not in VC — connect only (text granted on join)
            overwrites[target] = get_trusted_overwrite()

    # 6. Members currently in VC — text access (skip already handled)
    handled_ids = {owner_id} | blocked_ids | trusted_ids
    for member_id in current_member_ids:
        if member_id in handled_ids:
            continue
        member = guild.get_member(member_id)
        if not member or member.bot:
            continue
        overwrites[member] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        )

    # 7. Bot — full access
    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
            connect=True,
            manage_channels=True,
            manage_permissions=True,
            send_messages=True,
            read_message_history=True,
            manage_messages=True,
        )

    return overwrites


async def sync_channel_permissions(channel: discord.VoiceChannel) -> bool:
    """
    Rebuild ALL Discord permission overwrites for a temp channel from DB state.

    This is THE function. Every action that changes channel state calls this
    after updating the DB. It computes the full overwrite dict and applies it
    atomically via channel.edit(overwrites=...).

    Serialized per-channel via lock to prevent concurrent syncs racing.

    Args:
        channel: The Discord voice channel to sync.

    Returns:
        True if sync succeeded, False otherwise.
    """
    async with get_channel_lock(channel.id):
        guild = channel.guild
        current_member_ids = {m.id for m in channel.members if not m.bot}

        overwrites = compute_overwrites(guild, channel.id, current_member_ids)
        if overwrites is None:
            return False

        try:
            await channel.edit(overwrites=overwrites)
            logger.tree("Permissions Synced", [
                ("Channel", channel.name),
                ("Overwrites", str(len(overwrites))),
                ("Members In VC", str(len(current_member_ids))),
            ], emoji="🔒")
            return True
        except discord.HTTPException as e:
            logger.error_tree("Permission Sync Failed", e, [
                ("Channel", channel.name),
                ("Channel ID", str(channel.id)),
                ("Overwrites", str(len(overwrites))),
            ])
            return False


async def sync_all_channels(bot: discord.Client) -> None:
    """
    Sync permissions for ALL temp channels from DB state.

    Called on startup and after gateway reconnects to fix any drift.
    """
    all_channels = db.get_all_temp_channels()
    if not all_channels:
        logger.tree("Full Permission Sync Skipped", [
            ("Reason", "No temp channels in DB"),
        ], emoji="ℹ️")
        return

    synced = 0
    failed = 0
    missing = 0

    for channel_data in all_channels:
        channel_id = channel_data["channel_id"]
        guild_id = channel_data.get("guild_id", config.GUILD_ID)

        guild = bot.get_guild(guild_id)
        if not guild:
            continue

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            # Channel no longer exists — clean up DB
            db.delete_temp_channel(channel_id)
            missing += 1
            continue

        try:
            success = await sync_channel_permissions(channel)
            if success:
                synced += 1
            else:
                failed += 1
        except Exception as e:
            logger.error_tree("Channel Sync Error", e, [
                ("Channel ID", str(channel_id)),
            ])
            failed += 1

    logger.tree("Full Permission Sync Complete", [
        ("Synced", str(synced)),
        ("Failed", str(failed)),
        ("Missing (cleaned)", str(missing)),
        ("Total", str(len(all_channels))),
    ], emoji="🔄")


async def grant_text_access(channel: discord.VoiceChannel, member: discord.Member) -> None:
    """
    Grant text chat access to a member who just joined a temp VC.

    This is an additive operation — it only adds text permissions for this member
    without rebuilding the full overwrite set. Used by voice_state_update on join.

    Blocked users are rejected and kicked.

    Args:
        channel: The voice channel joined.
        member: The member who joined.
    """
    channel_info = db.get_temp_channel(channel.id)
    if not channel_info:
        return

    owner_id = channel_info["owner_id"]

    # Blocked user — re-apply block overwrite and kick
    if member.id in db.get_blocked_list(owner_id):
        try:
            await channel.set_permissions(member, overwrite=get_blocked_overwrite())
            if member.voice and member.voice.channel == channel:
                await member.move_to(None)
                logger.tree("Blocked User Auto-Kicked", [
                    ("Channel", channel.name),
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                    ("Owner", str(owner_id)),
                ], emoji="🚫")
        except discord.NotFound:
            logger.tree("Blocked Kick Skipped", [
                ("Channel", channel.name),
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Reason", "Channel or member not found"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            logger.error_tree("Blocked Kick Failed", e, [
                ("Channel", channel.name),
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])
        return

    # Don't override owner permissions
    if member.id == owner_id:
        logger.tree("Text Access Skipped", [
            ("Channel", channel.name),
            ("User", f"{member.name} ({member.display_name})"),
            ("Reason", "Member is owner"),
        ], emoji="⏭️")
        return

    # Grant text access
    try:
        overwrites = channel.overwrites_for(member)
        overwrites.view_channel = True
        overwrites.send_messages = True
        overwrites.read_message_history = True
        await channel.set_permissions(member, overwrite=overwrites)
        logger.tree("Text Access Granted", [
            ("Channel", channel.name),
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
        ], emoji="💬")
    except discord.NotFound:
        logger.tree("Text Access Grant Skipped", [
            ("Channel", channel.name),
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
            ("Reason", "Channel or member not found"),
        ], emoji="⚠️")
    except discord.HTTPException as e:
        logger.error_tree("Text Access Grant Failed", e, [
            ("Channel", channel.name),
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
        ])


async def revoke_text_access(channel: discord.VoiceChannel, member: discord.Member) -> None:
    """
    Revoke text chat access from a member who left a temp VC.

    Trusted users keep connect but lose text. Non-trusted users lose all overwrites.

    Args:
        channel: The voice channel left.
        member: The member who left.
    """
    channel_info = db.get_temp_channel(channel.id)
    if not channel_info:
        return

    owner_id = channel_info["owner_id"]

    # Don't revoke from owner
    if member.id == owner_id:
        return

    try:
        is_trusted = member.id in db.get_trusted_list(owner_id)
        if is_trusted:
            # Keep connect so they can rejoin, but revoke text
            await channel.set_permissions(member, overwrite=discord.PermissionOverwrite(
                connect=True,
            ))
        else:
            # Remove all custom permissions
            await channel.set_permissions(member, overwrite=None)
        logger.tree("Text Access Revoked", [
            ("Channel", channel.name),
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
            ("Trusted", str(is_trusted)),
        ], emoji="🔇")
    except discord.NotFound:
        logger.tree("Text Access Revoke Skipped", [
            ("Channel", channel.name),
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
            ("Reason", "Channel or member not found"),
        ], emoji="⚠️")
    except discord.HTTPException as e:
        logger.error_tree("Text Access Revoke Failed", e, [
            ("Channel", channel.name),
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
        ])
