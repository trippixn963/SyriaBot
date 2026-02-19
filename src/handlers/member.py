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
        if member.bot:
            return

        # Only track in main server
        if member.guild.id != config.GUILD_ID:
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
            logger.tree("Member Joined", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Role Given", role.name),
                ("Invited By", str(inviter_id) if inviter_id else "Unknown"),
            ], emoji="👋")
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

        # Mark user as inactive for leaderboard
        try:
            db.set_user_inactive(member.id, member.guild.id)
            logger.tree("Member Left", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Action", "Marked inactive on leaderboard"),
            ], emoji="👋")
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
        """Called when a member is updated - detects new boosts."""
        # Only track in main server
        if after.guild.id != config.GUILD_ID:
            return

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
            self._invalidate_api_cache(after.id)
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
                logger.tree("Boost Ended", [
                    ("User", f"{after.name} ({after.id})"),
                    ("Guild", after.guild.name),
                ], emoji="💔")
            except Exception as e:
                logger.tree("Unboost Record Failed", [
                    ("User", f"{after.name} ({after.id})"),
                    ("Type", "unboost"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
            # Invalidate API cache for this user
            self._invalidate_api_cache(after.id)

            # Broadcast updated boost count via WebSocket
            try:
                ws_manager = get_ws_manager()
                if ws_manager.connection_count > 0:
                    boost_count = after.guild.premium_subscription_count or 0
                    await ws_manager.broadcast_stat("boosts", boost_count)
            except Exception as e:
                logger.error_tree("WS Boost Broadcast Error", e)

    def _invalidate_api_cache(self, user_id: int) -> None:
        """Invalidate API caches when user's boost status changes."""
        try:
            from src.services import stats_api
            # Remove from avatar cache (contains booster status)
            if user_id in stats_api._avatar_cache:
                del stats_api._avatar_cache[user_id]
            # Clear response cache (leaderboard/stats contain booster info)
            stats_api._response_cache.clear()
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
        logger.tree("New Boost", [
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
            ("Guild", member.guild.name),
        ], emoji="💎")

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


async def setup(bot: commands.Bot) -> None:
    """Register the members handler cog with the bot."""
    await bot.add_cog(MembersHandler(bot))
    logger.tree("Handler Loaded", [
        ("Name", "MembersHandler"),
    ], emoji="✅")
