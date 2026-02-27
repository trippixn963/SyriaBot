"""
SyriaBot - Members Handler
==========================

Handles member join/leave/update events.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""


import asyncio

import discord
from discord.ext import commands

from src.core.config import config
from src.core.colors import COLOR_BOOST, COLOR_SYRIA_GREEN
from src.core.logger import logger
from src.services.database import db
from src.api.services.websocket import get_ws_manager
from src.api.services.event_logger import event_logger
from src.utils.footer import set_footer


class MembersHandler(commands.Cog):
    """
    Handler for member join/leave/update events.

    DESIGN:
        Tracks member joins with invite attribution.
        Handles boost events with special announcements.
        Manages auto-role assignment on join.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the members handler.

        Sets up invite tracking cache for join attribution.

        Args:
            bot: Main bot instance for Discord API access.
        """
        self.bot = bot
        # Cache invites for tracking: {invite_code: uses}
        self._invite_cache: dict[str, int] = {}
        # Flag to prevent duplicate caching on reconnects
        self._invites_cached: bool = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Cache invites on bot ready (only once, not on reconnects)."""
        if not self._invites_cached:
            await self._cache_invites()

    async def _cache_invites(self) -> None:
        """Cache all invites for the main guild."""
        if not config.GUILD_ID:
            return

        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            return

        try:
            # Add timeout to prevent hanging
            invites = await asyncio.wait_for(guild.invites(), timeout=10.0)
            self._invite_cache = {inv.code: inv.uses for inv in invites}
            self._invites_cached = True
            logger.tree("Invite Cache Loaded", [
                ("Guild", guild.name),
                ("Invites Cached", str(len(self._invite_cache))),
            ], emoji="🔗")
        except asyncio.TimeoutError:
            logger.tree("Invite Cache Timeout", [
                ("Guild", guild.name),
                ("Timeout", "10s"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            logger.tree("Invite Cache Failed", [
                ("Error", str(e)[:100]),
            ], emoji="⚠️")

    async def _find_used_invite(self, guild: discord.Guild) -> discord.Invite | None:
        """
        Find which invite was used by comparing with cache.

        Args:
            guild: The guild to check invites for

        Returns:
            The invite that was used, or None if not found
        """
        try:
            # Add timeout to prevent hanging
            new_invites = await asyncio.wait_for(guild.invites(), timeout=10.0)
            for invite in new_invites:
                cached_uses = self._invite_cache.get(invite.code, 0)
                if invite.uses > cached_uses:
                    # This invite was used, update cache
                    self._invite_cache[invite.code] = invite.uses
                    return invite

            # Update cache with any new invites
            self._invite_cache = {inv.code: inv.uses for inv in new_invites}
        except asyncio.TimeoutError:
            logger.tree("Invite Fetch Timeout", [
                ("Guild", guild.name),
                ("Timeout", "10s"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            logger.tree("Invite Fetch Failed", [
                ("Guild", guild.name),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Called when a member joins the server."""
        # Only track in main server
        if member.guild.id != config.GUILD_ID:
            return

        # Log bot additions separately
        if member.bot:
            # Try to find who added the bot from audit log
            added_by = None
            try:
                async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add):
                    if entry.target and entry.target.id == member.id:
                        added_by = entry.user
                        break
            except discord.Forbidden:
                pass
            event_logger.log_bot_add(member, added_by)
            return

        # Track who invited them
        inviter_id = None
        invite = await self._find_used_invite(member.guild)
        if invite and invite.inviter:
            inviter_id = invite.inviter.id
            try:
                db.set_invited_by(member.id, member.guild.id, inviter_id)
                logger.tree("Invite Tracked", [
                    ("New Member", f"{member.name} ({member.id})"),
                    ("Invited By", f"{invite.inviter.name} ({inviter_id})"),
                    ("Invite Code", invite.code),
                ], emoji="🔗")
            except Exception as e:
                logger.tree("Invite Track Failed", [
                    ("New Member", f"{member.name} ({member.id})"),
                    ("Inviter ID", str(inviter_id)),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        # Track new member for daily stats
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
            db.increment_new_members(member.guild.id, today)
        except Exception as e:
            logger.tree("New Member Track Failed", [
                ("Member", f"{member.name} ({member.id})"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Record member join event for growth tracking
        try:
            db.record_member_event(member.guild.id, member.id, "join")
        except Exception as e:
            logger.tree("Member Event Track Failed", [
                ("Member", f"{member.name} ({member.id})"),
                ("Event", "join"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Give auto-role
        if not config.AUTO_ROLE_ID:
            return

        role = member.guild.get_role(config.AUTO_ROLE_ID)
        if not role:
            logger.tree("Auto-Role Not Found", [
                ("Role ID", str(config.AUTO_ROLE_ID)),
                ("Guild", member.guild.name),
            ], emoji="⚠️")
            return

        try:
            await member.add_roles(role, reason="Auto-role on join")
            # Log to events system (for dashboard Events tab)
            event_logger.log_join(
                member=member,
                invite_code=invite.code if invite else None,
                inviter=invite.inviter if invite else None,
            )
        except discord.HTTPException as e:
            logger.tree("Auto-Role Failed", [
                ("User", f"{member.name} ({member.id})"),
                ("Role", role.name),
                ("Error", str(e)[:50]),
            ], emoji="❌")

        # Restore XP roles if they had any (for returning members)
        if hasattr(self.bot, 'xp_service') and self.bot.xp_service:
            try:
                await self.bot.xp_service.restore_member_roles(member)
            except Exception as e:
                logger.tree("XP Role Restore Error", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        # Mark user as active for leaderboard (returning members)
        try:
            db.set_user_active(member.id, member.guild.id)
        except Exception as e:
            logger.tree("Set User Active Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Send welcome DM
        await self._send_welcome_dm(member)

        # Broadcast updated member count via WebSocket
        try:
            ws_manager = get_ws_manager()
            if ws_manager.connection_count > 0:
                await ws_manager.broadcast_stat("members", member.guild.member_count)
        except Exception as e:
            logger.error_tree("WS Member Broadcast Error", e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Called when a member leaves/is kicked/banned."""
        if member.bot:
            return

        # Only track in main server
        if member.guild.id != config.GUILD_ID:
            return

        # Record member leave event for growth tracking
        try:
            db.record_member_event(member.guild.id, member.id, "leave")
        except Exception as e:
            logger.tree("Member Event Track Failed", [
                ("Member", f"{member.name} ({member.id})"),
                ("Event", "leave"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Mark user as inactive for leaderboard
        try:
            db.set_user_inactive(member.id, member.guild.id)

            # Check if this was a kick (not a ban - bans are logged in on_member_ban)
            was_kicked = False
            kick_moderator = None
            kick_reason = None
            try:
                async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                    if entry.target and entry.target.id == member.id:
                        # Check if this kick was recent (within 5 seconds)
                        from datetime import datetime, timezone
                        if (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 5:
                            was_kicked = True
                            kick_moderator = entry.user
                            kick_reason = entry.reason
                            break
            except discord.Forbidden:
                pass

            # Log to events system (for dashboard Events tab)
            if was_kicked:
                event_logger.log_kick(member.guild, member, kick_moderator, kick_reason)
            else:
                role_names = [r.name for r in member.roles if r.name != "@everyone"]
                event_logger.log_leave(member=member, roles=role_names)
        except Exception as e:
            logger.tree("Set User Inactive Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Broadcast updated member count via WebSocket
        try:
            ws_manager = get_ws_manager()
            if ws_manager.connection_count > 0:
                await ws_manager.broadcast_stat("members", member.guild.member_count)
        except Exception as e:
            logger.error_tree("WS Member Broadcast Error", e)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Called when a member is updated - detects boosts, roles, timeouts, nicknames."""
        # Only track in main server
        if after.guild.id != config.GUILD_ID:
            return

        # Track role changes
        added_roles = set(after.roles) - set(before.roles)
        removed_roles = set(before.roles) - set(after.roles)

        for role in added_roles:
            if role.name != "@everyone":
                event_logger.log_role_add(after, role)

        for role in removed_roles:
            if role.name != "@everyone":
                event_logger.log_role_remove(after, role)

        # Track nickname changes
        if before.nick != after.nick:
            event_logger.log_nick_change(after, before.nick, after.nick)

        # Track timeout changes
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until is not None:
                # Member was timed out
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                if after.timed_out_until > now:
                    delta = after.timed_out_until - now
                    if delta.days > 0:
                        duration = f"{delta.days}d"
                    elif delta.seconds >= 3600:
                        duration = f"{delta.seconds // 3600}h"
                    else:
                        duration = f"{delta.seconds // 60}m"
                    event_logger.log_timeout(after, duration=duration)
            else:
                # Timeout was removed
                event_logger.log_timeout_remove(after)

        # Check if member started boosting
        if before.premium_since is None and after.premium_since is not None:
            # Record boost in history
            try:
                db.record_boost(after.id, after.guild.id, "boost")
            except Exception as e:
                logger.tree("Boost Record Failed", [
                    ("User", f"{after.name} ({after.id})"),
                    ("Type", "boost"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
            # Invalidate API cache for this user
            await self._invalidate_api_cache(after.id)
            await self._handle_new_boost(after)

            # Broadcast updated boost count via WebSocket
            try:
                ws_manager = get_ws_manager()
                if ws_manager.connection_count > 0:
                    boost_count = after.guild.premium_subscription_count or 0
                    await ws_manager.broadcast_stat("boosts", boost_count)
            except Exception as e:
                logger.error_tree("WS Boost Broadcast Error", e)

        # Check if member stopped boosting
        elif before.premium_since is not None and after.premium_since is None:
            try:
                db.record_boost(after.id, after.guild.id, "unboost")
                # Log to events system (for dashboard Events tab)
                event_logger.log_unboost(after)
            except Exception as e:
                logger.tree("Unboost Record Failed", [
                    ("User", f"{after.name} ({after.id})"),
                    ("Type", "unboost"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
            # Invalidate API cache for this user
            await self._invalidate_api_cache(after.id)

            # Broadcast updated boost count via WebSocket
            try:
                ws_manager = get_ws_manager()
                if ws_manager.connection_count > 0:
                    boost_count = after.guild.premium_subscription_count or 0
                    await ws_manager.broadcast_stat("boosts", boost_count)
            except Exception as e:
                logger.error_tree("WS Boost Broadcast Error", e)

    async def _invalidate_api_cache(self, user_id: int) -> None:
        """Invalidate API caches when user's boost status changes."""
        try:
            if not self.bot.stats_api:
                return
            cache = self.bot.stats_api.cache
            await cache.remove_avatar(user_id)
            await cache.clear_responses()
            logger.tree("API Cache Invalidated", [
                ("ID", str(user_id)),
                ("Reason", "Boost status changed"),
            ], emoji="🔄")
        except Exception as e:
            logger.tree("API Cache Invalidate Failed", [
                ("ID", str(user_id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    async def _handle_new_boost(self, member: discord.Member) -> None:
        """Send thank you message when someone boosts."""
        # Log to events system (for dashboard Events tab)
        event_logger.log_boost(member)

        # Get general channel
        if not config.GENERAL_CHANNEL_ID:
            logger.tree("Boost Notification Skipped", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Reason", "GENERAL_CHANNEL_ID not configured"),
            ], emoji="⚠️")
            return

        channel = member.guild.get_channel(config.GENERAL_CHANNEL_ID)
        if not channel:
            logger.tree("Boost Notification Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Reason", "General channel not found"),
                ("Channel ID", str(config.GENERAL_CHANNEL_ID)),
            ], emoji="⚠️")
            return

        # Get boost count
        boost_count = member.guild.premium_subscription_count or 0

        # Build the thank you embed
        embed = discord.Embed(
            title="New Server Booster!",
            description=(
                f"Thank you {member.mention} for boosting **{member.guild.name}**!\n\n"
                f"We now have **{boost_count}** boosts!"
            ),
            color=COLOR_BOOST
        )

        # Feature unlocks field
        embed.add_field(
            name="Booster Perks",
            value=(
                "• **2x XP** on messages and voice\n"
                "• **No cooldowns** on commands\n"
                "• **Unlimited** `/download` and `/image`\n"
                "• **AI Translation** via `/translate`"
            ),
            inline=False
        )

        # Set booster avatar as thumbnail
        embed.set_thumbnail(url=member.display_avatar.url)

        set_footer(embed)

        try:
            await channel.send(content=member.mention, embed=embed)
            logger.tree("Boost Notification Sent", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Channel", channel.name),
            ], emoji="✅")
        except discord.HTTPException as e:
            logger.tree("Boost Notification Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Error", str(e)[:100]),
            ], emoji="❌")

    async def _send_welcome_dm(self, member: discord.Member) -> None:
        """Send a welcome DM to new members with server info and commands."""
        # Build rules channel mention
        rules_text = f"<#{config.RULES_CHANNEL_ID}>" if config.RULES_CHANNEL_ID else "the rules"

        embed = discord.Embed(
            title=f"Welcome to {member.guild.name}!",
            description=(
                f"Hey {member.display_name}, we're glad to have you here!\n\n"
                f"Please read {rules_text} before chatting."
            ),
            color=COLOR_SYRIA_GREEN
        )

        embed.add_field(
            name="Useful Commands",
            value=(
                "`/rank` — Check your level and XP\n"
                "`/confess` — Share anonymously\n"
                "`/download` — Download social media videos\n"
                "`/birthday set` — Register your birthday"
            ),
            inline=False
        )

        embed.add_field(
            name="Earn XP",
            value=(
                "Chat in channels and join voice calls to earn XP.\n"
                "Level up to unlock new permissions!"
            ),
            inline=False
        )

        embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else None)
        set_footer(embed)

        try:
            await member.send(embed=embed)
            logger.tree("Welcome DM Sent", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ], emoji="📬")
        except discord.Forbidden:
            logger.tree("Welcome DM Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Reason", "DMs disabled"),
            ], emoji="ℹ️")
        except discord.HTTPException as e:
            logger.tree("Welcome DM Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        """Called when a member is banned."""
        if guild.id != config.GUILD_ID:
            return

        # Try to get moderator from audit log
        moderator = None
        reason = None
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                if entry.target and entry.target.id == user.id:
                    moderator = entry.user
                    reason = entry.reason
                    break
        except discord.Forbidden:
            pass

        event_logger.log_ban(guild, user, moderator, reason)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        """Called when a member is unbanned."""
        if guild.id != config.GUILD_ID:
            return

        # Try to get moderator from audit log
        moderator = None
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
                if entry.target and entry.target.id == user.id:
                    moderator = entry.user
                    break
        except discord.Forbidden:
            pass

        event_logger.log_unban(guild, user, moderator)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        """Called when an invite is created."""
        if not invite.guild or invite.guild.id != config.GUILD_ID:
            return

        event_logger.log_invite_create(invite)

        # Update invite cache
        self._invite_cache[invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        """Called when an invite is deleted."""
        if not invite.guild or invite.guild.id != config.GUILD_ID:
            return

        event_logger.log_invite_delete(invite)

        # Remove from cache
        self._invite_cache.pop(invite.code, None)


async def setup(bot: commands.Bot) -> None:
    """Register the members handler cog with the bot."""
    await bot.add_cog(MembersHandler(bot))
    logger.tree("Handler Loaded", [
        ("Name", "MembersHandler"),
    ], emoji="✅")
