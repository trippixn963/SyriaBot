"""
SyriaBot - TempVoice Panel
===========================

Panel embed building, updating, and sticky resend logic for TempVoice channels.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord

from src.core.colors import (
    EMOJI_LOCK, EMOJI_UNLOCK, EMOJI_LIMIT, EMOJI_RENAME, EMOJI_ALLOW,
    EMOJI_TRANSFER, EMOJI_DELETE,
    COLOR_ERROR, COLOR_SUCCESS,
)
from src.core.config import config
from src.core.logger import logger
from src.services.database import db
from .graphics import render_voice_guide
from .views import TempVoiceControlPanel

if TYPE_CHECKING:
    from .service import TempVoiceService


_last_status: dict[int, str] = {}  # channel_id -> last status text (debounce)
_voice_guide_url: str | None = None  # Permanent CDN URL for voice guide image


async def ensure_voice_guide_url(bot) -> str | None:
    """Upload voice guide to asset channel once, cache the CDN URL forever."""
    global _voice_guide_url

    if _voice_guide_url:
        return _voice_guide_url

    if not config.ASSET_STORAGE_CHANNEL_ID:
        logger.tree("Voice Guide Skipped", [("Reason", "No asset channel configured")], emoji="⚠️")
        return None

    guild = bot.get_guild(config.GUILD_ID)
    if not guild:
        logger.tree("Voice Guide Skipped", [("Reason", "Guild not cached"), ("ID", str(config.GUILD_ID))], emoji="⚠️")
        return None

    asset_channel = guild.get_channel(config.ASSET_STORAGE_CHANNEL_ID)
    if not asset_channel:
        try:
            asset_channel = await bot.fetch_channel(config.ASSET_STORAGE_CHANNEL_ID)
        except Exception:
            pass
    if not asset_channel:
        logger.tree("Voice Guide Skipped", [("Reason", "Asset channel not found"), ("ID", str(config.ASSET_STORAGE_CHANNEL_ID))], emoji="⚠️")
        return None

    try:
        import io
        voice_bytes = await render_voice_guide()
        if not voice_bytes:
            logger.tree("Voice Guide Skipped", [("Reason", "Render returned empty")], emoji="⚠️")
            return None

        msg = await asset_channel.send(
            content="Voice Guide (permanent asset — do not delete)",
            file=discord.File(io.BytesIO(voice_bytes), "voice_guide.png"),
        )
        if msg.attachments:
            _voice_guide_url = msg.attachments[0].url
            logger.tree("Voice Guide Uploaded", [
                ("URL", _voice_guide_url[:80]),
            ], emoji="🖼️")
            return _voice_guide_url
    except Exception as e:
        logger.error_tree("Voice Guide Upload Failed", e)

    return None


async def update_voice_status(channel: discord.VoiceChannel) -> None:
    """
    Update the voice channel status text shown in Discord's channel list.

    Shows a rich status with lock, allowed count, and activity hint.
    Debounced: skips if status hasn't changed since last update.

    Called after: creation, lock/unlock, member join/leave, limit change, transfer.
    """
    channel_info = db.get_temp_channel(channel.id)
    if not channel_info:
        return

    is_locked: bool = bool(channel_info.get("is_locked", 0))
    owner_id: int = channel_info["owner_id"]
    member_count: int = len([m for m in channel.members if not m.bot])

    # Build status — clean and short
    lock_text = "🔒 Private" if is_locked else "🔓 Public"

    if member_count == 0:
        vibe = "💤 Empty"
    elif member_count == 1:
        vibe = "🎧 Solo"
    elif member_count <= 3:
        vibe = "💬 Chilling"
    elif member_count <= 6:
        vibe = "🔥 Active"
    else:
        vibe = "🎉 Party"

    status = f"{lock_text} ・ {vibe}"

    # Debounce: skip if unchanged
    if _last_status.get(channel.id) == status:
        return
    _last_status[channel.id] = status

    try:
        await channel.edit(status=status)
        logger.tree("VC Status Updated", [
            ("Channel", channel.name),
            ("Status", status),
        ], emoji="📊")
    except discord.NotFound:
        _last_status.pop(channel.id, None)
    except discord.HTTPException as e:
        logger.error_tree("VC Status Update Failed", e, [
            ("Channel", channel.name),
            ("Status", status),
        ])


def clear_voice_status_cache(channel_id: int) -> None:
    """Remove cached status for a deleted channel."""
    _last_status.pop(channel_id, None)


def build_panel_embed(
    channel: discord.VoiceChannel,
    owner: discord.Member,
    is_locked: bool = True,
) -> discord.Embed:
    """Build the control panel embed.

    Reads trusted/blocked lists from DB (not Discord overwrites).
    """
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
        status = f"{EMOJI_LOCK} Locked"
        color = COLOR_ERROR
    else:
        status = f"{EMOJI_UNLOCK} Unlocked"
        color = COLOR_SUCCESS

    description = (
        f"**Owner:** {owner.mention} ・ **Status:** {status}\n"
        f"**Members:** {member_count}/{limit} ・ **Bitrate:** {bitrate} kbps\n"
        f"**Created:** {duration_text} ・ **Allowed:** {len(valid_trusted)}"
    )

    embed = discord.Embed(
        title=channel.name,
        description=description,
        color=color,
    )

    embed.set_thumbnail(url=owner.display_avatar.url)

    # Voice guide as permanent image (CDN URL survives embed edits)
    if _voice_guide_url:
        embed.set_image(url=_voice_guide_url)

    return embed


def build_panel_view(service: "TempVoiceService", is_locked: bool = True) -> TempVoiceControlPanel:
    """Build a fresh control panel view with correct lock button state.

    Creates a new TempVoiceControlPanel instance each time to avoid race
    conditions when multiple channels update concurrently. The persistent
    view registered via bot.add_view() handles interactions for old messages
    after restarts; these per-message instances handle live interactions.
    """
    view = TempVoiceControlPanel(service)
    view.lock_button.label = "Locked" if is_locked else "Unlocked"
    view.lock_button.emoji = EMOJI_LOCK if is_locked else EMOJI_UNLOCK
    return view



async def send_channel_interface(
    channel: discord.VoiceChannel,
    owner: discord.Member,
    service: "TempVoiceService",
) -> discord.Message:
    """Send guide images + control panel + welcome message to voice channel."""
    # Ensure voice guide CDN URL exists (lazy upload on first use)
    await ensure_voice_guide_url(service.bot)

    auto_lock = owner.id == config.OWNER_ID or owner.id in config.VC_AUTO_LOCK_USERS
    embed = build_panel_embed(channel, owner, is_locked=auto_lock)

    message = await channel.send(
        embed=embed,
        view=build_panel_view(service, is_locked=auto_lock),
    )

    # Divider under control panel
    from src.utils.divider import send_divider
    await send_divider(channel)

    # Welcome message with rules reminder and music info
    welcome = (
        f"### Welcome to your voice channel, {owner.mention}!\n"
        f"Use the **control panel** above to manage your channel.\n\n"
        f"<:rules:1460257117977055283> **Rules**\n"
        f"- Voice channels are **self-moderated** by the owner\n"
        f"- Be respectful to everyone in your channel\n"
        f"- No mic spamming or soundboards abuse\n"
        f"- Follow all server rules at all times\n"
        f"- Mods can join locked channels\n\n"
        f"<:music:1480176122582012097> **Music**\n"
        f"We use **Boogie Premium** for music! Type `/play` to get started."
    )
    await channel.send(welcome)

    # Send divider image to separate setup from chat
    await send_divider(channel)

    # Cache message ID
    db.update_temp_channel(channel.id, panel_message_id=message.id)

    # Set VC status (visible in Discord's channel list)
    await update_voice_status(channel)

    logger.tree("Channel Interface Sent", [
        ("Channel", channel.name),
        ("Owner", f"{owner.name} ({owner.display_name})"),
        ("Panel ID", str(message.id)),
        ("Auto-Lock", str(auto_lock)),
    ], emoji="🎛️")

    return message


async def update_panel(channel: discord.VoiceChannel, service: "TempVoiceService") -> None:
    """Update the control panel embed in the channel using cached message ID."""
    # Use per-channel lock to prevent duplicate panels from concurrent updates
    lock = _get_panel_lock(channel.id, service)
    async with lock:
        await _update_panel_inner(channel, service)


def _get_panel_lock(channel_id: int, service: "TempVoiceService") -> asyncio.Lock:
    """Get or create a lock for panel updates on a specific channel."""
    if channel_id not in service._panel_locks:
        service._panel_locks[channel_id] = asyncio.Lock()
    return service._panel_locks[channel_id]


async def _update_panel_inner(channel: discord.VoiceChannel, service: "TempVoiceService") -> None:
    """Inner panel update logic (called with lock held)."""
    # Skip if panel creation is in progress (prevents race with _create_temp_channel)
    if channel.id in service._pending_panels:
        return

    channel_info = db.get_temp_channel(channel.id)
    if not channel_info:
        # Channel exists in Discord but not in DB - will be cleaned up when empty
        logger.tree("Panel Update Skipped", [("Channel ID", str(channel.id))], emoji="ℹ️")
        return

    owner = channel.guild.get_member(channel_info["owner_id"])
    if not owner:
        logger.tree("Panel Update Skipped", [
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
            embed = build_panel_embed(channel, owner, is_locked)
            await message.edit(embed=embed, view=build_panel_view(service, is_locked))
            return
        except discord.NotFound:
            logger.debug("Panel Message Not Found — will recreate", [
                ("Channel", channel.name),
                ("Message ID", str(panel_message_id)),
            ])
        except discord.HTTPException as e:
            logger.error_tree("Panel Update Failed", e, [
                ("Channel", channel.name),
            ])

    # Fallback: Search through recent messages (slow path)
    panel_found = False
    try:
        # Safety check - bot.user can be None during startup
        if not service.bot.user:
            logger.tree("Panel Update Skipped", [
                ("Channel", channel.name),
                ("Reason", "Bot not ready"),
            ], emoji="⚠️")
            return

        async for message in channel.history(limit=50):
            if (message.author.id == service.bot.user.id and message.embeds
                    and message.embeds[0].description and "**Owner:**" in message.embeds[0].description):
                embed = build_panel_embed(channel, owner, is_locked)
                await message.edit(embed=embed, view=build_panel_view(service, is_locked))
                # Cache the message ID for next time
                db.update_temp_channel(channel.id, panel_message_id=message.id)
                panel_found = True
                break
    except discord.NotFound:
        # Channel was deleted — clean up DB
        db.delete_temp_channel(channel.id)
        logger.tree("Panel Update Aborted", [
            ("Channel", channel.name),
            ("Reason", "Channel deleted"),
            ("Action", "DB entry cleaned up"),
        ], emoji="🗑️")
        return
    except discord.HTTPException as e:
        logger.error_tree("Panel History Search Failed", e, [
            ("Channel", channel.name),
        ])

    # Panel was deleted - recreate panel only (guides are still in channel)
    if not panel_found:
        try:
            embed = build_panel_embed(channel, owner, is_locked)
            message = await channel.send(embed=embed, view=build_panel_view(service, is_locked))
            db.update_temp_channel(channel.id, panel_message_id=message.id)

            logger.tree("Panel Recovered", [
                ("Channel", channel.name),
                ("Owner", str(owner)),
            ], emoji="🔧")
        except discord.NotFound:
            # Channel was deleted — clean up DB
            db.delete_temp_channel(channel.id)
            logger.tree("Panel Recovery Aborted", [
                ("Channel", channel.name),
                ("Reason", "Channel deleted"),
                ("Action", "DB entry cleaned up"),
            ], emoji="🗑️")
        except discord.HTTPException as e:
            logger.error_tree("Panel Recovery Failed", e, [
                ("Channel", channel.name),
            ])


async def resend_sticky_panel(channel: discord.VoiceChannel, service: "TempVoiceService") -> None:
    """Delete old panel and resend as sticky message."""
    # Use per-channel lock to prevent races with update_panel
    lock = _get_panel_lock(channel.id, service)
    async with lock:
        channel_info = db.get_temp_channel(channel.id)
        if not channel_info:
            return

        owner = channel.guild.get_member(channel_info["owner_id"])
        if not owner:
            logger.tree("Sticky Panel Skipped", [
                ("Channel", channel.name),
                ("Reason", "Owner not found"),
            ], emoji="⚠️")
            return

        # Delete old guide images and panel (keep welcome message with owner ping)
        # Scan all bot messages — delete images (guides) and embeds with "Owner" field (panel)
        try:
            bot_id = service.bot.user.id if service.bot.user else None
            if bot_id:
                async for msg in channel.history(limit=50):
                    if msg.author.id != bot_id:
                        continue
                    is_guide = msg.attachments and any(a.filename == "voice_guide.png" for a in msg.attachments)
                    is_panel = msg.embeds and any(e.description and "**Owner:**" in e.description for e in msg.embeds)
                    if is_guide or is_panel:
                        try:
                            await msg.delete()
                        except discord.NotFound:
                            pass
                        except discord.HTTPException as e:
                            logger.error_tree("Sticky Panel Old Message Delete Failed", e, [
                                ("Channel", channel.name),
                                ("Message ID", str(msg.id)),
                            ])
        except discord.NotFound:
            logger.tree("Sticky Panel Scan Skipped", [
                ("Channel", channel.name),
                ("Reason", "Channel not found during history scan"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            logger.error_tree("Sticky Panel History Scan Failed", e, [
                ("Channel", channel.name),
            ])

        # Send new guides + panel (no owner ping on resend)
        try:
            is_locked = bool(channel_info.get("is_locked", 0))

            embed = build_panel_embed(channel, owner, is_locked)
            new_message = await channel.send(embed=embed, view=build_panel_view(service, is_locked))

            # Cache new message ID
            db.update_temp_channel(channel.id, panel_message_id=new_message.id)

            logger.tree("Sticky Panel Resent", [
                ("Channel", channel.name),
                ("Owner", str(owner)),
            ], emoji="📌")
        except discord.HTTPException as e:
            logger.error_tree("Sticky Panel Failed", e, [
                ("Channel", channel.name),
            ])


async def resend_interface_panel(channel: discord.TextChannel, service: "TempVoiceService") -> None:
    """Delete old interface panel and resend as sticky message in interface channel.

    NOTE: Caller (on_message) already holds the panel lock for this channel.
    Do NOT re-acquire it here or it will deadlock.
    """
    # Find and delete ALL bot messages (old panels)
    try:
        async for msg in channel.history(limit=50):
            if msg.author.id == service.bot.user.id:
                try:
                    await msg.delete()
                except discord.NotFound:
                    pass
                except discord.HTTPException as e:
                    logger.error_tree("Interface Panel Old Message Delete Failed", e, [
                        ("Channel", channel.name),
                        ("Message ID", str(msg.id)),
                    ])
    except discord.NotFound:
        logger.tree("Interface Panel Scan Skipped", [
            ("Channel", channel.name),
            ("Reason", "Channel not found during history scan"),
        ], emoji="⚠️")
    except discord.HTTPException as e:
        logger.error_tree("Interface Panel History Scan Failed", e, [
            ("Channel", channel.name),
        ])

    # Build and send new interface panel
    embed = discord.Embed(
        title="🎙️ TempVoice",
        description=(
            f"Create your own temporary voice channel!\n\n"
            f"**How to use:**\n"
            f"Join <#{config.VC_CREATOR_CHANNEL_ID}> to create your channel\n\n"
            f"**Features:**\n"
            f"• {EMOJI_LOCK} Lock/Unlock your channel\n"
            f"• {EMOJI_LIMIT} Set user limit\n"
            f"• {EMOJI_RENAME} Rename your channel\n"
            f"• {EMOJI_ALLOW} Allow/Block users\n"
            f"• {EMOJI_TRANSFER} Transfer ownership\n"
            f"• {EMOJI_DELETE} Delete your channel"
        ),
        color=COLOR_SUCCESS,
    )

    try:
        await channel.send(embed=embed)
        logger.tree("Interface Panel Resent", [
            ("Channel", channel.name),
        ], emoji="📌")
    except discord.HTTPException as e:
        logger.error_tree("Interface Panel Failed", e, [
            ("Channel", channel.name),
        ])
