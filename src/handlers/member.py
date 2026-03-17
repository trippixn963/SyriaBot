"""
SyriaBot - Members Handler
==========================

Handles member join/leave/update events.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""


import asyncio
import random
import re
import time
from pathlib import Path

import discord
from discord.ext import commands

from src.core.config import config
from src.core.colors import COLOR_BOOST, COLOR_GOLD, COLOR_SYRIA_GREEN
from src.core.logger import logger
from src.services.database import db
from src.services.actions import action_service
from src.api.services.websocket import get_ws_manager
from src.api.services.event_logger import event_logger

WELCOME_BANNER = Path(__file__).resolve().parent.parent.parent / "assets" / "welcome" / "welcome.png"

WAVE_MESSAGES = [
    "{user} waves at {target}",
    "{user} waves hello to {target}",
    "{user} says hi to {target}",
]

WELCOME_GREETINGS = [
    "ahlan wa sahlan",
    "ya hala",
    "nawwart",
    "ahla w sahla",
    "tfaddal",
    "marhaba",
    "hayyak allah",
    "ya marhaba",
    "ahlan fik",
    "sharraftna",
]


# Track who already waved per welcome message: {message_id: {user_id, ...}}
_wave_tracker: dict[int, set[int]] = {}
_WAVE_TRACKER_MAX = 200  # Max tracked messages before cleanup

# Per-user cooldown for wave button (seconds)
_WAVE_COOLDOWN = 5
_wave_cooldowns: dict[int, float] = {}


def _cleanup_wave_tracker() -> None:
    """Evict oldest entries if tracker is too large."""
    while len(_wave_tracker) > _WAVE_TRACKER_MAX:
        oldest = next(iter(_wave_tracker))
        _wave_tracker.pop(oldest, None)

    # Clean expired cooldowns (>5s old) to prevent unbounded growth
    now = time.monotonic()
    expired = [uid for uid, ts in _wave_cooldowns.items() if now - ts > _WAVE_COOLDOWN]
    for uid in expired:
        _wave_cooldowns.pop(uid, None)


class WaveButton(discord.ui.DynamicItem[discord.ui.Button], template=r"wave:(?P<member_id>\d+)"):
    """Persistent wave button that survives bot restarts. One wave per user per welcome."""

    def __init__(self, member_id: int):
        self.member_id = member_id
        super().__init__(
            discord.ui.Button(
                label="Wave to say hi!",
                style=discord.ButtonStyle.secondary,
                custom_id=f"wave:{member_id}",
                emoji="👋",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> "WaveButton":
        return cls(int(match.group("member_id")))

    async def callback(self, interaction: discord.Interaction) -> None:
        user_id = interaction.user.id
        msg_id = interaction.message.id if interaction.message else 0

        # One wave per user per welcome message
        if msg_id in _wave_tracker and user_id in _wave_tracker[msg_id]:
            await interaction.response.send_message(
                "You already waved!", ephemeral=True,
            )
            return

        # Per-user cooldown
        now = time.monotonic()
        last_used = _wave_cooldowns.get(user_id, 0)
        if now - last_used < _WAVE_COOLDOWN:
            await interaction.response.send_message(
                "Slow down! Try again in a few seconds.", ephemeral=True,
            )
            return

        # Mark as waved and set cooldown before deferring
        _wave_tracker.setdefault(msg_id, set()).add(user_id)
        _wave_cooldowns[user_id] = now
        _cleanup_wave_tracker()

        await interaction.response.defer()

        try:
            gif_url = await action_service.get_action_gif("wave")
            if not gif_url:
                return

            action_text = random.choice(WAVE_MESSAGES).format(
                user=interaction.user.mention,
                target=f"<@{self.member_id}>",
            )
            embed = discord.Embed(description=action_text, color=COLOR_GOLD)
            embed.set_image(url=gif_url)
            await interaction.channel.send(embed=embed)
        except discord.HTTPException:
            pass


class WaveView(discord.ui.View):
    """View wrapper for the wave button."""

    def __init__(self, member_id: int):
        super().__init__(timeout=None)
        self.add_item(WaveButton(member_id).item)


class MemberHandler(commands.Cog):
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
        self._invite_lock = asyncio.Lock()
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
        except asyncio.TimeoutError as e:
            logger.error_tree("Invite Cache Timeout", e, [
                ("Guild", guild.name),
                ("Timeout", "10s"),
            ])
        except discord.HTTPException as e:
            logger.error_tree("Invite Cache Failed", e, [
                ("Guild", guild.name),
            ])

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
            async with self._invite_lock:
                for invite in new_invites:
                    cached_uses = self._invite_cache.get(invite.code, 0)
                    if invite.uses > cached_uses:
                        # This invite was used, update cache
                        self._invite_cache[invite.code] = invite.uses
                        return invite

                # Update cache with any new invites
                self._invite_cache = {inv.code: inv.uses for inv in new_invites}
        except asyncio.TimeoutError as e:
            logger.error_tree("Invite Fetch Timeout", e, [
                ("Guild", guild.name),
                ("Timeout", "10s"),
            ])
        except discord.HTTPException as e:
            logger.error_tree("Invite Fetch Failed", e, [
                ("Guild", guild.name),
            ])

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
                logger.error_tree("Invite Track Failed", e, [
                    ("New Member", f"{member.name} ({member.id})"),
                    ("Inviter ID", str(inviter_id)),
                ])

        # Track new member for daily stats
        try:
            from datetime import datetime
            from src.core.constants import TIMEZONE_EST
            today = datetime.now(TIMEZONE_EST).strftime("%Y-%m-%d")
            db.increment_new_members(member.guild.id, today)
        except Exception as e:
            logger.error_tree("New Member Track Failed", e, [
                ("Member", f"{member.name} ({member.id})"),
            ])

        # Record member join event for growth tracking
        try:
            db.record_member_event(member.guild.id, member.id, "join")
        except Exception as e:
            logger.error_tree("Member Event Track Failed", e, [
                ("Member", f"{member.name} ({member.id})"),
                ("Event", "join"),
            ])

        # Give auto-role
        if config.AUTO_ROLE_ID:
            role = member.guild.get_role(config.AUTO_ROLE_ID)
            if role:
                try:
                    await member.add_roles(role, reason="Auto-role on join")
                    # Log to events system (for dashboard Events tab)
                    event_logger.log_join(
                        member=member,
                        invite_code=invite.code if invite else None,
                        inviter=invite.inviter if invite else None,
                    )
                except discord.HTTPException as e:
                    logger.error_tree("Auto-Role Failed", e, [
                        ("User", f"{member.name} ({member.id})"),
                        ("Role", role.name),
                    ])
            else:
                logger.tree("Auto-Role Not Found", [
                    ("Role ID", str(config.AUTO_ROLE_ID)),
                    ("Guild", member.guild.name),
                ], emoji="⚠️")

        # Restore XP roles if they had any (for returning members)
        if hasattr(self.bot, 'xp_service') and self.bot.xp_service:
            try:
                await self.bot.xp_service.restore_member_roles(member)
            except Exception as e:
                logger.error_tree("XP Role Restore Error", e, [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                ])

        # Mark user as active for leaderboard (returning members)
        try:
            db.set_user_active(member.id, member.guild.id)
        except Exception as e:
            logger.error_tree("Set User Active Failed", e, [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])

        # Send welcome DM
        await self._send_welcome_dm(member)

        # Send welcome message in general chat
        await self._send_welcome_message(member)

        # Broadcast updated member count via WebSocket
        try:
            ws_manager = get_ws_manager()
            if ws_manager.connection_count > 0:
                await ws_manager.broadcast_stat("members", member.guild.member_count)
        except Exception as e:
            logger.error_tree("WS Member Broadcast Error", e)

    async def _send_welcome_message(self, member: discord.Member) -> None:
        """Send a welcome message in general chat with a wave button."""
        if not config.GENERAL_CHANNEL_ID:
            return

        channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
        if not channel:
            return

        try:
            created_ts = int(member.created_at.timestamp())
            greeting = random.choice(WELCOME_GREETINGS)
            embed = discord.Embed(
                description=(
                    f"• Check the rules in <#{config.RULES_CHANNEL_ID}>\n"
                    f"• Grab free roles in <#{config.ROLE_SHOP_CHANNEL_ID}>\n\n"
                    f"<:claim:1455709985467011173> Account created <t:{created_ts}:R>"
                ),
                color=COLOR_SYRIA_GREEN,
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            view = WaveView(member.id)
            await channel.send(
                content=f"{member.mention} {greeting}!",
                embed=embed,
                view=view,
            )
            logger.tree("Welcome Message Sent", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Channel", channel.name),
            ], emoji="👋")
        except discord.HTTPException as e:
            logger.error_tree("Welcome Message Failed", e, [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Called when a member leaves/is kicked/banned."""
        if member.bot:
            return

        # Only track in main server
        if member.guild.id != config.GUILD_ID:
            return

        # Remove from roulette activity tracking
        if self.bot.roulette_service:
            self.bot.roulette_service._user_activity.pop(member.id, None)

        # Clean up family data (divorce, orphan children, remove from parent)
        try:
            result = db.cleanup_family_on_leave(member.id, member.guild.id)
            total = result["divorces"] + result["orphaned_children"] + result["removed_from_parent"]
            if total > 0:
                logger.tree("Family Cleanup on Leave", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                    ("Divorces", str(result["divorces"])),
                    ("Orphaned Children", str(result["orphaned_children"])),
                    ("Removed from Parent", str(result["removed_from_parent"])),
                ], emoji="👪")
        except Exception as e:
            logger.error_tree("Family Cleanup Failed", e, [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])

        # Record member leave event for growth tracking
        try:
            db.record_member_event(member.guild.id, member.id, "leave")
        except Exception as e:
            logger.error_tree("Member Event Track Failed", e, [
                ("Member", f"{member.name} ({member.id})"),
                ("Event", "leave"),
            ])

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
            logger.error_tree("Set User Inactive Failed", e, [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])

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
                logger.error_tree("Boost Record Failed", e, [
                    ("User", f"{after.name} ({after.id})"),
                    ("Type", "boost"),
                ])
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
                logger.error_tree("Unboost Record Failed", e, [
                    ("User", f"{after.name} ({after.id})"),
                    ("Type", "unboost"),
                ])
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
            logger.error_tree("API Cache Invalidate Failed", e, [
                ("ID", str(user_id)),
            ])

    async def _handle_new_boost(self, member: discord.Member) -> None:
        """Send thank you DM when someone boosts."""
        # Log to events system (for dashboard Events tab)
        event_logger.log_boost(member)

        guild = member.guild
        boost_count = guild.premium_subscription_count or 0

        embed = discord.Embed(
            title="Thank You for Boosting!",
            description=f"You just boosted **{guild.name}**! Here's what you unlocked:",
            color=COLOR_BOOST,
        )

        embed.add_field(
            name="XP",
            value="`2x` on messages & voice",
            inline=True,
        )
        embed.add_field(
            name="Downloads",
            value="`Unlimited` /download",
            inline=True,
        )
        embed.add_field(
            name="Image Search",
            value="`Unlimited` /image",
            inline=True,
        )
        embed.add_field(
            name="Commands",
            value="`No cooldowns` on all commands",
            inline=True,
        )
        embed.add_field(
            name="Translation",
            value="`AI Translation` via /translate",
            inline=True,
        )
        embed.set_thumbnail(url=guild.icon.url if guild.icon else member.display_avatar.url)

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(
            label="Leaderboard",
            style=discord.ButtonStyle.link,
            url=config.LEADERBOARD_BASE_URL,
            emoji="🏆",
        ))

        try:
            await member.send(embed=embed, view=view)
            logger.tree("Boost DM Sent", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ], emoji="💎")
        except discord.Forbidden:
            logger.tree("Boost DM Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Reason", "DMs disabled"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            logger.error_tree("Boost DM Failed", e, [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])

    async def _send_welcome_dm(self, member: discord.Member) -> None:
        """Send a welcome DM to new members with server info and commands."""
        vc_text = f"<#{config.VC_CREATOR_CHANNEL_ID}>" if config.VC_CREATOR_CHANNEL_ID else "the VC creator"

        embed = discord.Embed(
            title="Syrian Arab Republic",
            description=(
                f"Ahlan {member.display_name}, welcome to the family!\n\n"
                f"\u2022 Pick your roles via <id:customize>\n"
                f"\u2022 Grab a free custom role in <#{config.ROLE_SHOP_CHANNEL_ID}>\n"
                f"\u2022 Join {vc_text} to make your own voice chat"
            ),
            color=COLOR_GOLD
        )

        if member.guild.banner:
            embed.set_image(url=member.guild.banner.url)

        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.link,
            label="Rules",
            url=f"https://discord.com/channels/{member.guild.id}/{config.RULES_CHANNEL_ID}",
            emoji=discord.PartialEmoji(name="rules", id=1460257117977055283),
        ))
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.link,
            label="Leaderboard",
            url=config.LEADERBOARD_BASE_URL,
            emoji=discord.PartialEmoji(name="leaderboard", id=1456582433033162927),
        ))

        try:
            await member.send(file=discord.File(WELCOME_BANNER), embed=embed, view=view)
            logger.tree("Welcome DM Sent", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ], emoji="📬")
        except discord.Forbidden as e:
            logger.error_tree("Welcome DM Failed", e, [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Reason", "DMs disabled"),
            ])
        except discord.HTTPException as e:
            logger.error_tree("Welcome DM Failed", e, [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])

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
    await bot.add_cog(MemberHandler(bot))
    logger.tree("Handler Loaded", [
        ("Name", "MemberHandler"),
    ], emoji="✅")
