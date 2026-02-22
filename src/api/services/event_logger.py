"""
SyriaBot - Event Logger
=======================

High-level interface for logging Discord events.
Logs to both console (via logger) and database.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import functools
from datetime import datetime
from typing import Any, Dict, List, Optional

import discord

from src.core.logger import logger


# =============================================================================
# Helpers
# =============================================================================

def _safe_log(func):
    """Decorator to prevent logging errors from crashing the caller."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.tree("Event Log Error", [
                ("Method", func.__name__),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")
            return 0
    return wrapper


def _get_avatar_url(user: discord.User | discord.Member | None) -> Optional[str]:
    """Get avatar URL, preferring guild-specific avatar."""
    if not user:
        return None
    if isinstance(user, discord.Member) and user.guild_avatar:
        return user.guild_avatar.url
    if user.avatar:
        return user.avatar.url
    return user.default_avatar.url


def _get_display_name(user: discord.User | discord.Member | None) -> Optional[str]:
    """Get display name, showing nickname if available."""
    if not user:
        return None
    if isinstance(user, discord.Member) and user.nick:
        return f"{user.nick} ({user.name})"
    return user.name


def _truncate(text: Optional[str], max_len: int = 50) -> str:
    """Truncate text for console display."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


# =============================================================================
# Event Logger
# =============================================================================

class EventLogger:
    """High-level event logger that writes to console and database."""

    def __init__(self):
        self._storage = None

    def _get_storage(self):
        """Lazy-load storage to avoid import issues."""
        if self._storage is None:
            from src.api.services.event_storage import get_event_storage
            self._storage = get_event_storage()
        return self._storage

    def _log(
        self,
        event_type: str,
        guild: discord.Guild,
        title: str,
        emoji: str,
        log_items: List[tuple],
        actor: Optional[discord.User | discord.Member] = None,
        target: Optional[discord.User | discord.Member] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Core logging method."""
        # Console log
        logger.tree(title, log_items, emoji=emoji)

        # Database log
        return self._get_storage().add(
            event_type=event_type,
            guild_id=guild.id,
            actor_id=actor.id if actor else None,
            actor_name=_get_display_name(actor),
            actor_avatar=_get_avatar_url(actor),
            target_id=target.id if target else None,
            target_name=_get_display_name(target),
            target_avatar=_get_avatar_url(target),
            channel_id=channel.id if channel else None,
            channel_name=channel.name if channel else None,
            reason=reason,
            details=details,
        )

    # =========================================================================
    # Member Events
    # =========================================================================

    @_safe_log
    def log_join(
        self,
        member: discord.Member,
        invite_code: Optional[str] = None,
        inviter: Optional[discord.User] = None,
    ) -> int:
        """Log member join event."""
        from src.api.services.event_storage import EventType

        # Calculate account age
        account_age = (datetime.utcnow() - member.created_at.replace(tzinfo=None)).days

        details = {
            "account_age_days": account_age,
            "bot": member.bot,
        }
        if invite_code:
            details["invite_code"] = invite_code
        if inviter:
            details["inviter_id"] = str(inviter.id)
            details["inviter_name"] = inviter.name

        log_items = [
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
            ("Account Age", f"{account_age} days"),
        ]
        if invite_code:
            log_items.append(("Invite", invite_code))
        if inviter:
            log_items.append(("Invited By", inviter.name))

        return self._log(
            event_type=EventType.MEMBER_JOIN,
            guild=member.guild,
            title="Member Joined",
            emoji="📥",
            log_items=log_items,
            target=member,
            actor=inviter,
            details=details,
        )

    @_safe_log
    def log_leave(
        self,
        member: discord.Member,
        roles: Optional[List[str]] = None,
    ) -> int:
        """Log member leave event."""
        from src.api.services.event_storage import EventType

        # Calculate membership duration
        if member.joined_at:
            duration = (datetime.utcnow() - member.joined_at.replace(tzinfo=None)).days
        else:
            duration = 0

        details = {
            "membership_days": duration,
            "roles": roles or [],
        }

        return self._log(
            event_type=EventType.MEMBER_LEAVE,
            guild=member.guild,
            title="Member Left",
            emoji="📤",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Duration", f"{duration} days"),
            ],
            target=member,
            details=details,
        )

    @_safe_log
    def log_ban(
        self,
        guild: discord.Guild,
        target: discord.User,
        moderator: Optional[discord.User] = None,
        reason: Optional[str] = None,
    ) -> int:
        """Log member ban event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MEMBER_BAN,
            guild=guild,
            title="Member Banned",
            emoji="🔨",
            log_items=[
                ("User", f"{target.name}"),
                ("ID", str(target.id)),
                ("Moderator", moderator.name if moderator else "Unknown"),
                ("Reason", _truncate(reason) or "No reason"),
            ],
            actor=moderator,
            target=target,
            reason=reason,
        )

    @_safe_log
    def log_unban(
        self,
        guild: discord.Guild,
        target: discord.User,
        moderator: Optional[discord.User] = None,
    ) -> int:
        """Log member unban event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MEMBER_UNBAN,
            guild=guild,
            title="Member Unbanned",
            emoji="🔓",
            log_items=[
                ("User", f"{target.name}"),
                ("ID", str(target.id)),
                ("Moderator", moderator.name if moderator else "Unknown"),
            ],
            actor=moderator,
            target=target,
        )

    @_safe_log
    def log_kick(
        self,
        guild: discord.Guild,
        target: discord.User,
        moderator: Optional[discord.User] = None,
        reason: Optional[str] = None,
    ) -> int:
        """Log member kick event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MEMBER_KICK,
            guild=guild,
            title="Member Kicked",
            emoji="👢",
            log_items=[
                ("User", f"{target.name}"),
                ("ID", str(target.id)),
                ("Moderator", moderator.name if moderator else "Unknown"),
                ("Reason", _truncate(reason) or "No reason"),
            ],
            actor=moderator,
            target=target,
            reason=reason,
        )

    @_safe_log
    def log_boost(self, member: discord.Member) -> int:
        """Log member boost event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MEMBER_BOOST,
            guild=member.guild,
            title="Server Boosted",
            emoji="💎",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Boost Level", str(member.guild.premium_tier)),
            ],
            target=member,
            details={"boost_level": member.guild.premium_tier},
        )

    @_safe_log
    def log_unboost(self, member: discord.Member) -> int:
        """Log member unboost event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MEMBER_UNBOOST,
            guild=member.guild,
            title="Boost Removed",
            emoji="💔",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ],
            target=member,
        )

    # =========================================================================
    # Voice Events
    # =========================================================================

    @_safe_log
    def log_voice_join(
        self,
        member: discord.Member,
        channel: discord.VoiceChannel,
        member_count: int,
    ) -> int:
        """Log voice channel join event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.VOICE_JOIN,
            guild=member.guild,
            title="Voice Join",
            emoji="🔊",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("Channel", channel.name),
                ("Members", str(member_count)),
            ],
            target=member,
            channel=channel,
            details={"member_count": member_count},
        )

    @_safe_log
    def log_voice_leave(
        self,
        member: discord.Member,
        channel: discord.VoiceChannel,
        duration_minutes: int,
    ) -> int:
        """Log voice channel leave event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.VOICE_LEAVE,
            guild=member.guild,
            title="Voice Leave",
            emoji="🔇",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("Channel", channel.name),
                ("Duration", f"{duration_minutes} min"),
            ],
            target=member,
            channel=channel,
            details={"duration_minutes": duration_minutes},
        )

    @_safe_log
    def log_voice_switch(
        self,
        member: discord.Member,
        from_channel: discord.VoiceChannel,
        to_channel: discord.VoiceChannel,
    ) -> int:
        """Log voice channel switch event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.VOICE_SWITCH,
            guild=member.guild,
            title="Voice Switch",
            emoji="🔀",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("From", from_channel.name),
                ("To", to_channel.name),
            ],
            target=member,
            channel=to_channel,
            details={
                "from_channel_id": str(from_channel.id),
                "from_channel_name": from_channel.name,
            },
        )

    # =========================================================================
    # Channel Events
    # =========================================================================

    @_safe_log
    def log_channel_create(
        self,
        channel: discord.abc.GuildChannel,
        creator: Optional[discord.Member] = None,
    ) -> int:
        """Log channel creation event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.CHANNEL_CREATE,
            guild=channel.guild,
            title="Channel Created",
            emoji="📁",
            log_items=[
                ("Channel", channel.name),
                ("Type", str(channel.type)),
                ("Creator", creator.name if creator else "Unknown"),
            ],
            actor=creator,
            channel=channel,
            details={"channel_type": str(channel.type)},
        )

    @_safe_log
    def log_channel_delete(
        self,
        channel: discord.abc.GuildChannel,
        deleter: Optional[discord.Member] = None,
    ) -> int:
        """Log channel deletion event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.CHANNEL_DELETE,
            guild=channel.guild,
            title="Channel Deleted",
            emoji="📁",
            log_items=[
                ("Channel", channel.name),
                ("Type", str(channel.type)),
                ("Deleted By", deleter.name if deleter else "Unknown"),
            ],
            actor=deleter,
            details={"channel_type": str(channel.type), "channel_name": channel.name},
        )

    # =========================================================================
    # Server Events
    # =========================================================================

    @_safe_log
    def log_bump(self, guild: discord.Guild) -> int:
        """Log server bump event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.SERVER_BUMP,
            guild=guild,
            title="Server Bumped",
            emoji="📢",
            log_items=[
                ("Source", "Disboard"),
            ],
        )

    # =========================================================================
    # Thread Events
    # =========================================================================

    @_safe_log
    def log_thread_create(
        self,
        thread: discord.Thread,
        owner: Optional[discord.Member] = None,
    ) -> int:
        """Log thread creation event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.THREAD_CREATE,
            guild=thread.guild,
            title="Thread Created",
            emoji="🧵",
            log_items=[
                ("Name", thread.name),
                ("Owner", str(thread.owner_id)),
                ("Parent", thread.parent.name if thread.parent else "Unknown"),
            ],
            actor=owner,
            channel=thread,
            details={
                "parent_id": str(thread.parent_id) if thread.parent_id else None,
                "parent_name": thread.parent.name if thread.parent else None,
            },
        )

    # =========================================================================
    # XP Events
    # =========================================================================

    @_safe_log
    def log_level_up(
        self,
        member: discord.Member,
        old_level: int,
        new_level: int,
        channel: Optional[discord.abc.GuildChannel] = None,
    ) -> int:
        """Log level up event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.XP_LEVEL_UP,
            guild=member.guild,
            title="Level Up",
            emoji="🎉",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("Level", f"{old_level} → {new_level}"),
            ],
            target=member,
            channel=channel,
            details={
                "old_level": old_level,
                "new_level": new_level,
            },
        )

    # =========================================================================
    # Message Events
    # =========================================================================

    @_safe_log
    def log_message_delete(
        self,
        guild: discord.Guild,
        channel: discord.abc.GuildChannel,
        author: Optional[discord.User | discord.Member] = None,
        content: Optional[str] = None,
        moderator: Optional[discord.User | discord.Member] = None,
    ) -> int:
        """Log message deletion event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MESSAGE_DELETE,
            guild=guild,
            title="Message Deleted",
            emoji="🗑️",
            log_items=[
                ("Channel", channel.name),
                ("Author", author.name if author else "Unknown"),
                ("By", moderator.name if moderator else "Author/Unknown"),
            ],
            actor=moderator or author,
            target=author,
            channel=channel,
            details={"content_preview": _truncate(content, 100)} if content else None,
        )

    @_safe_log
    def log_bulk_delete(
        self,
        guild: discord.Guild,
        channel: discord.abc.GuildChannel,
        count: int,
        moderator: Optional[discord.User | discord.Member] = None,
    ) -> int:
        """Log bulk message deletion event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MESSAGE_BULK_DELETE,
            guild=guild,
            title="Bulk Delete",
            emoji="🗑️",
            log_items=[
                ("Channel", channel.name),
                ("Messages", str(count)),
                ("By", moderator.name if moderator else "Unknown"),
            ],
            actor=moderator,
            channel=channel,
            details={"message_count": count},
        )

    @_safe_log
    def log_message_edit(
        self,
        guild: discord.Guild,
        channel: discord.abc.GuildChannel,
        author: discord.User | discord.Member,
        before_content: Optional[str] = None,
        after_content: Optional[str] = None,
    ) -> int:
        """Log message edit event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MESSAGE_EDIT,
            guild=guild,
            title="Message Edited",
            emoji="✏️",
            log_items=[
                ("Channel", channel.name),
                ("Author", author.name),
            ],
            target=author,
            channel=channel,
            details={
                "before_preview": _truncate(before_content, 100) if before_content else None,
                "after_preview": _truncate(after_content, 100) if after_content else None,
            },
        )

    # =========================================================================
    # Role Events
    # =========================================================================

    @_safe_log
    def log_role_add(
        self,
        member: discord.Member,
        role: discord.Role,
        moderator: Optional[discord.User | discord.Member] = None,
    ) -> int:
        """Log role added to member event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MEMBER_ROLE_ADD,
            guild=member.guild,
            title="Role Added",
            emoji="🏷️",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("Role", role.name),
                ("By", moderator.name if moderator else "Unknown"),
            ],
            actor=moderator,
            target=member,
            details={"role_id": str(role.id), "role_name": role.name},
        )

    @_safe_log
    def log_role_remove(
        self,
        member: discord.Member,
        role: discord.Role,
        moderator: Optional[discord.User | discord.Member] = None,
    ) -> int:
        """Log role removed from member event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MEMBER_ROLE_REMOVE,
            guild=member.guild,
            title="Role Removed",
            emoji="🏷️",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("Role", role.name),
                ("By", moderator.name if moderator else "Unknown"),
            ],
            actor=moderator,
            target=member,
            details={"role_id": str(role.id), "role_name": role.name},
        )

    # =========================================================================
    # Timeout Events
    # =========================================================================

    @_safe_log
    def log_timeout(
        self,
        member: discord.Member,
        moderator: Optional[discord.User | discord.Member] = None,
        duration: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> int:
        """Log member timeout event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MEMBER_TIMEOUT,
            guild=member.guild,
            title="Member Timed Out",
            emoji="⏱️",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("Duration", duration or "Unknown"),
                ("By", moderator.name if moderator else "Unknown"),
                ("Reason", _truncate(reason) or "No reason"),
            ],
            actor=moderator,
            target=member,
            reason=reason,
            details={"duration": duration} if duration else None,
        )

    @_safe_log
    def log_timeout_remove(
        self,
        member: discord.Member,
        moderator: Optional[discord.User | discord.Member] = None,
    ) -> int:
        """Log member timeout removed event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MEMBER_TIMEOUT_REMOVE,
            guild=member.guild,
            title="Timeout Removed",
            emoji="✅",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("By", moderator.name if moderator else "Unknown"),
            ],
            actor=moderator,
            target=member,
        )

    # =========================================================================
    # Nickname Events
    # =========================================================================

    @_safe_log
    def log_nick_change(
        self,
        member: discord.Member,
        old_nick: Optional[str],
        new_nick: Optional[str],
    ) -> int:
        """Log nickname change event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.MEMBER_NICK_CHANGE,
            guild=member.guild,
            title="Nickname Changed",
            emoji="✏️",
            log_items=[
                ("User", member.name),
                ("From", old_nick or "None"),
                ("To", new_nick or "None"),
            ],
            target=member,
            details={
                "old_nick": old_nick,
                "new_nick": new_nick,
            },
        )

    # =========================================================================
    # Voice Moderation Events
    # =========================================================================

    @_safe_log
    def log_voice_mute(
        self,
        member: discord.Member,
        moderator: Optional[discord.User | discord.Member] = None,
        muted: bool = True,
    ) -> int:
        """Log voice mute/unmute event."""
        from src.api.services.event_storage import EventType

        event_type = EventType.VOICE_MUTE if muted else EventType.VOICE_UNMUTE
        title = "Voice Muted" if muted else "Voice Unmuted"
        emoji = "🔇" if muted else "🔊"

        return self._log(
            event_type=event_type,
            guild=member.guild,
            title=title,
            emoji=emoji,
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("By", moderator.name if moderator else "Self"),
            ],
            actor=moderator,
            target=member,
        )

    @_safe_log
    def log_voice_deafen(
        self,
        member: discord.Member,
        moderator: Optional[discord.User | discord.Member] = None,
        deafened: bool = True,
    ) -> int:
        """Log voice deafen/undeafen event."""
        from src.api.services.event_storage import EventType

        event_type = EventType.VOICE_DEAFEN if deafened else EventType.VOICE_UNDEAFEN
        title = "Voice Deafened" if deafened else "Voice Undeafened"
        emoji = "🔇" if deafened else "🔊"

        return self._log(
            event_type=event_type,
            guild=member.guild,
            title=title,
            emoji=emoji,
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("By", moderator.name if moderator else "Self"),
            ],
            actor=moderator,
            target=member,
        )

    @_safe_log
    def log_voice_disconnect(
        self,
        member: discord.Member,
        channel: discord.VoiceChannel,
        moderator: Optional[discord.User | discord.Member] = None,
    ) -> int:
        """Log voice disconnect (by moderator) event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.VOICE_DISCONNECT,
            guild=member.guild,
            title="Voice Disconnected",
            emoji="🔇",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("Channel", channel.name),
                ("By", moderator.name if moderator else "Unknown"),
            ],
            actor=moderator,
            target=member,
            channel=channel,
        )

    # =========================================================================
    # Invite Events
    # =========================================================================

    @_safe_log
    def log_invite_create(
        self,
        invite: discord.Invite,
    ) -> int:
        """Log invite creation event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.INVITE_CREATE,
            guild=invite.guild,
            title="Invite Created",
            emoji="🔗",
            log_items=[
                ("Code", invite.code),
                ("Channel", invite.channel.name if invite.channel else "Unknown"),
                ("By", invite.inviter.name if invite.inviter else "Unknown"),
                ("Max Uses", str(invite.max_uses) if invite.max_uses else "Unlimited"),
            ],
            actor=invite.inviter,
            channel=invite.channel,
            details={
                "code": invite.code,
                "max_uses": invite.max_uses,
                "max_age": invite.max_age,
            },
        )

    @_safe_log
    def log_invite_delete(
        self,
        invite: discord.Invite,
    ) -> int:
        """Log invite deletion event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.INVITE_DELETE,
            guild=invite.guild,
            title="Invite Deleted",
            emoji="🔗",
            log_items=[
                ("Code", invite.code),
                ("Channel", invite.channel.name if invite.channel else "Unknown"),
            ],
            channel=invite.channel,
            details={"code": invite.code},
        )

    # =========================================================================
    # Bot Events
    # =========================================================================

    @_safe_log
    def log_bot_add(
        self,
        member: discord.Member,
        added_by: Optional[discord.User | discord.Member] = None,
    ) -> int:
        """Log bot added to server event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.BOT_ADD,
            guild=member.guild,
            title="Bot Added",
            emoji="🤖",
            log_items=[
                ("Bot", member.name),
                ("ID", str(member.id)),
                ("Added By", added_by.name if added_by else "Unknown"),
            ],
            actor=added_by,
            target=member,
        )

    # =========================================================================
    # XP Role Reward Event
    # =========================================================================

    @_safe_log
    def log_xp_role_reward(
        self,
        member: discord.Member,
        role: discord.Role,
        level: int,
    ) -> int:
        """Log XP role reward event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.XP_ROLE_REWARD,
            guild=member.guild,
            title="XP Role Reward",
            emoji="🎖️",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("Role", role.name),
                ("Level", str(level)),
            ],
            target=member,
            details={
                "role_id": str(role.id),
                "role_name": role.name,
                "level": level,
            },
        )

    # =========================================================================
    # Voice Streaming Events
    # =========================================================================

    @_safe_log
    def log_voice_stream_start(
        self,
        member: discord.Member,
        channel: discord.VoiceChannel,
    ) -> int:
        """Log voice stream start event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.VOICE_STREAM_START,
            guild=member.guild,
            title="Stream Started",
            emoji="📺",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("Channel", channel.name),
            ],
            target=member,
            channel=channel,
        )

    @_safe_log
    def log_voice_stream_end(
        self,
        member: discord.Member,
        channel: discord.VoiceChannel,
    ) -> int:
        """Log voice stream end event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.VOICE_STREAM_END,
            guild=member.guild,
            title="Stream Ended",
            emoji="📺",
            log_items=[
                ("User", f"{member.name} ({member.display_name})"),
                ("Channel", channel.name),
            ],
            target=member,
            channel=channel,
        )

    # =========================================================================
    # Thread Events
    # =========================================================================

    @_safe_log
    def log_thread_delete(
        self,
        thread: discord.Thread,
        deleter: Optional[discord.Member] = None,
    ) -> int:
        """Log thread deletion event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.THREAD_DELETE,
            guild=thread.guild,
            title="Thread Deleted",
            emoji="🧵",
            log_items=[
                ("Name", thread.name),
                ("Deleted By", deleter.name if deleter else "Unknown"),
                ("Parent", thread.parent.name if thread.parent else "Unknown"),
            ],
            actor=deleter,
            details={
                "thread_name": thread.name,
                "parent_id": str(thread.parent_id) if thread.parent_id else None,
            },
        )

    # =========================================================================
    # Role Events
    # =========================================================================

    @_safe_log
    def log_role_create(
        self,
        role: discord.Role,
        creator: Optional[discord.Member] = None,
    ) -> int:
        """Log role creation event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.ROLE_CREATE,
            guild=role.guild,
            title="Role Created",
            emoji="🎭",
            log_items=[
                ("Role", role.name),
                ("Color", str(role.color)),
                ("Created By", creator.name if creator else "Unknown"),
            ],
            actor=creator,
            details={
                "role_id": str(role.id),
                "role_name": role.name,
                "color": str(role.color),
            },
        )

    @_safe_log
    def log_role_delete(
        self,
        role: discord.Role,
        deleter: Optional[discord.Member] = None,
    ) -> int:
        """Log role deletion event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.ROLE_DELETE,
            guild=role.guild,
            title="Role Deleted",
            emoji="🎭",
            log_items=[
                ("Role", role.name),
                ("Deleted By", deleter.name if deleter else "Unknown"),
            ],
            actor=deleter,
            details={
                "role_id": str(role.id),
                "role_name": role.name,
            },
        )

    @_safe_log
    def log_role_update(
        self,
        before: discord.Role,
        after: discord.Role,
        updater: Optional[discord.Member] = None,
    ) -> int:
        """Log role update event."""
        from src.api.services.event_storage import EventType

        changes = []
        if before.name != after.name:
            changes.append(f"Name: {before.name} → {after.name}")
        if before.color != after.color:
            changes.append(f"Color: {before.color} → {after.color}")
        if before.permissions != after.permissions:
            changes.append("Permissions changed")

        return self._log(
            event_type=EventType.ROLE_UPDATE,
            guild=after.guild,
            title="Role Updated",
            emoji="🎭",
            log_items=[
                ("Role", after.name),
                ("Changes", ", ".join(changes) if changes else "Unknown"),
                ("Updated By", updater.name if updater else "Unknown"),
            ],
            actor=updater,
            details={
                "role_id": str(after.id),
                "role_name": after.name,
                "changes": changes,
            },
        )

    # =========================================================================
    # Emoji Events
    # =========================================================================

    @_safe_log
    def log_emoji_create(
        self,
        emoji: discord.Emoji,
        creator: Optional[discord.Member] = None,
    ) -> int:
        """Log emoji creation event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.EMOJI_CREATE,
            guild=emoji.guild,
            title="Emoji Created",
            emoji="😀",
            log_items=[
                ("Emoji", emoji.name),
                ("Created By", creator.name if creator else "Unknown"),
            ],
            actor=creator,
            details={
                "emoji_id": str(emoji.id),
                "emoji_name": emoji.name,
                "animated": emoji.animated,
            },
        )

    @_safe_log
    def log_emoji_delete(
        self,
        emoji: discord.Emoji,
        deleter: Optional[discord.Member] = None,
    ) -> int:
        """Log emoji deletion event."""
        from src.api.services.event_storage import EventType

        return self._log(
            event_type=EventType.EMOJI_DELETE,
            guild=emoji.guild,
            title="Emoji Deleted",
            emoji="😀",
            log_items=[
                ("Emoji", emoji.name),
                ("Deleted By", deleter.name if deleter else "Unknown"),
            ],
            actor=deleter,
            details={
                "emoji_id": str(emoji.id),
                "emoji_name": emoji.name,
            },
        )

    # =========================================================================
    # Generic Event
    # =========================================================================

    @_safe_log
    def log_event(
        self,
        event_type: str,
        guild: discord.Guild,
        title: str,
        emoji: str,
        log_items: List[tuple],
        actor: Optional[discord.User | discord.Member] = None,
        target: Optional[discord.User | discord.Member] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log a generic event."""
        return self._log(
            event_type=event_type,
            guild=guild,
            title=title,
            emoji=emoji,
            log_items=log_items,
            actor=actor,
            target=target,
            channel=channel,
            reason=reason,
            details=details,
        )


# =============================================================================
# Singleton
# =============================================================================

event_logger = EventLogger()

__all__ = ["event_logger", "EventLogger"]
