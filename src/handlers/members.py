"""
SyriaBot - Members Handler
==========================

Handles member join/leave/update events.

Author: حَـــــنَّـــــا
"""

from typing import Dict, Optional

import discord
from discord.ext import commands

from src.core.config import config
from src.core.logger import log
from src.services.database import db
from src.utils.footer import set_footer


class MembersHandler(commands.Cog):
    """Handles member events."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the members handler with bot reference and invite cache."""
        self.bot = bot
        # Cache invites for tracking: {invite_code: uses}
        self._invite_cache: Dict[str, int] = {}

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Cache invites on bot ready."""
        await self._cache_invites()

    async def _cache_invites(self) -> None:
        """Cache all invites for the main guild."""
        if not config.GUILD_ID:
            return

        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            return

        try:
            invites = await guild.invites()
            self._invite_cache = {inv.code: inv.uses for inv in invites}
            log.tree("Invite Cache Loaded", [
                ("Guild", guild.name),
                ("Invites Cached", str(len(self._invite_cache))),
            ], emoji="🔗")
        except discord.HTTPException as e:
            log.tree("Invite Cache Failed", [
                ("Error", str(e)[:100]),
            ], emoji="⚠️")

    async def _find_used_invite(self, guild: discord.Guild) -> Optional[discord.Invite]:
        """
        Find which invite was used by comparing with cache.

        Args:
            guild: The guild to check invites for

        Returns:
            The invite that was used, or None if not found
        """
        try:
            new_invites = await guild.invites()
            for invite in new_invites:
                cached_uses = self._invite_cache.get(invite.code, 0)
                if invite.uses > cached_uses:
                    # This invite was used, update cache
                    self._invite_cache[invite.code] = invite.uses
                    return invite

            # Update cache with any new invites
            self._invite_cache = {inv.code: inv.uses for inv in new_invites}
        except discord.HTTPException as e:
            log.tree("Invite Fetch Failed", [
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
                log.tree("Invite Tracked", [
                    ("New Member", f"{member.name} ({member.id})"),
                    ("Invited By", f"{invite.inviter.name} ({inviter_id})"),
                    ("Invite Code", invite.code),
                ], emoji="🔗")
            except Exception as e:
                log.tree("Invite Track Failed", [
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
            log.tree("New Member Track Failed", [
                ("Member", f"{member.name} ({member.id})"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Give auto-role
        if not config.AUTO_ROLE_ID:
            return

        role = member.guild.get_role(config.AUTO_ROLE_ID)
        if not role:
            log.tree("Auto-Role Not Found", [
                ("Role ID", str(config.AUTO_ROLE_ID)),
                ("Guild", member.guild.name),
            ], emoji="⚠️")
            return

        try:
            await member.add_roles(role, reason="Auto-role on join")
            log.tree("Member Joined", [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
                ("Role Given", role.name),
                ("Invited By", str(inviter_id) if inviter_id else "Unknown"),
            ], emoji="👋")
        except discord.HTTPException as e:
            log.tree("Auto-Role Failed", [
                ("User", f"{member.name} ({member.id})"),
                ("Role", role.name),
                ("Error", str(e)[:50]),
            ], emoji="❌")

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
                log.tree("Boost Record Failed", [
                    ("User", f"{after.name} ({after.id})"),
                    ("Type", "boost"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
            # Invalidate API cache for this user
            self._invalidate_api_cache(after.id)
            await self._handle_new_boost(after)

        # Check if member stopped boosting
        elif before.premium_since is not None and after.premium_since is None:
            try:
                db.record_boost(after.id, after.guild.id, "unboost")
                log.tree("Boost Ended", [
                    ("User", f"{after.name} ({after.id})"),
                    ("Guild", after.guild.name),
                ], emoji="💔")
            except Exception as e:
                log.tree("Unboost Record Failed", [
                    ("User", f"{after.name} ({after.id})"),
                    ("Type", "unboost"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
            # Invalidate API cache for this user
            self._invalidate_api_cache(after.id)

    def _invalidate_api_cache(self, user_id: int) -> None:
        """Invalidate API caches when user's boost status changes."""
        try:
            from src.services import stats_api
            # Remove from avatar cache (contains booster status)
            if user_id in stats_api._avatar_cache:
                del stats_api._avatar_cache[user_id]
            # Clear response cache (leaderboard/stats contain booster info)
            stats_api._response_cache.clear()
            log.tree("API Cache Invalidated", [
                ("User ID", str(user_id)),
                ("Reason", "Boost status changed"),
            ], emoji="🔄")
        except Exception as e:
            log.tree("API Cache Invalidate Failed", [
                ("User ID", str(user_id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    async def _handle_new_boost(self, member: discord.Member) -> None:
        """Send thank you message when someone boosts."""
        log.tree("New Boost", [
            ("User", f"{member.name} ({member.display_name})"),
            ("User ID", str(member.id)),
            ("Guild", member.guild.name),
        ], emoji="💎")

        # Get general channel
        if not config.GENERAL_CHANNEL_ID:
            log.tree("Boost Notification Skipped", [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
                ("Reason", "GENERAL_CHANNEL_ID not configured"),
            ], emoji="⚠️")
            return

        channel = member.guild.get_channel(config.GENERAL_CHANNEL_ID)
        if not channel:
            log.tree("Boost Notification Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
                ("Reason", "General channel not found"),
                ("Channel ID", str(config.GENERAL_CHANNEL_ID)),
            ], emoji="⚠️")
            return

        # Build the thank you embed
        embed = discord.Embed(
            title="💎 New Server Booster!",
            description=(
                f"Thank you {member.mention} for boosting **{member.guild.name}**!\n\n"
                f"Your support helps keep the community thriving!"
            ),
            color=0x2ECC71  # Green
        )

        # Feature unlocks field
        embed.add_field(
            name="🏆 Booster Perks Unlocked",
            value=(
                "• **2x XP** on all messages and voice activity\n"
                "• **No cooldowns** on commands\n"
                "• **AI Translation** powered by GPT-4o"
            ),
            inline=False
        )

        # Check DMs reminder
        embed.add_field(
            name="📬 Check Your DMs",
            value="Other bots may have sent you additional perks and rewards!",
            inline=False
        )

        # Set booster avatar as thumbnail
        embed.set_thumbnail(url=member.display_avatar.url)

        # Gold accent on the side (using author field for visual appeal)
        embed.set_author(
            name="Server Boost",
            icon_url="https://cdn.discordapp.com/emojis/857628597716910100.webp"  # Boost emoji
        )

        set_footer(embed)

        try:
            await channel.send(content=member.mention, embed=embed)
            log.tree("Boost Notification Sent", [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
                ("Channel", channel.name),
            ], emoji="✅")
        except discord.HTTPException as e:
            log.tree("Boost Notification Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
                ("Error", str(e)[:100]),
            ], emoji="❌")


async def setup(bot: commands.Bot) -> None:
    """Register the members handler cog with the bot."""
    await bot.add_cog(MembersHandler(bot))
    log.tree("Handler Loaded", [
        ("Name", "MembersHandler"),
    ], emoji="✅")
