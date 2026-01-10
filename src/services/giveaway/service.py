"""
SyriaBot - Giveaway Service
===========================

Giveaway system with customizable prizes and requirements.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import json
import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import discord
from zoneinfo import ZoneInfo

from src.core.config import config, ROOT_DIR
from src.core.logger import log
from src.core.colors import COLOR_SYRIA_GREEN, COLOR_SUCCESS, COLOR_ERROR, EMOJI_GIVEAWAY
from src.services.database import db

# Asset paths
GIVEAWAY_IMAGE_PATH = ROOT_DIR / "assets" / "giveaway.gif"
GIVEAWAY_EMOJI_URL = "https://cdn.discordapp.com/emojis/1459518392674549882.png"
from src.utils.footer import set_footer

if TYPE_CHECKING:
    from src.bot import SyriaBot


# =============================================================================
# Constants
# =============================================================================

TIMEZONE = ZoneInfo("America/New_York")

# Prize types
PRIZE_TYPES = {
    "xp": "XP",
    "coins": "Casino Coins",
    "nitro": "Discord Nitro",
    "role": "Role",
    "custom": "Custom Prize",
}

# Duration options (label, timedelta)
DURATION_OPTIONS = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
    "48h": timedelta(hours=48),
    "7d": timedelta(days=7),
}

# Winner count options
WINNER_OPTIONS = [1, 2, 3, 5, 10]

# Check interval for expired giveaways
CHECK_INTERVAL = 30  # seconds

# Booster bonus multiplier (2x entries)
BOOSTER_MULTIPLIER = 2


class GiveawayService:
    """Service for managing giveaways."""

    def __init__(self, bot: "SyriaBot") -> None:
        """Initialize the giveaway service."""
        self.bot: "SyriaBot" = bot
        self._running: bool = False
        self._check_task: Optional[asyncio.Task] = None

    async def setup(self) -> None:
        """Initialize the giveaway service."""
        if not config.GIVEAWAY_CHANNEL_ID:
            log.tree("Giveaway Service", [
                ("Status", "Disabled"),
                ("Reason", "Missing GIVEAWAY_CHANNEL_ID"),
            ], emoji="ℹ️")
            return

        channel = self.bot.get_channel(config.GIVEAWAY_CHANNEL_ID)
        if not channel:
            log.tree("Giveaway Service", [
                ("Status", "Warning"),
                ("Reason", "Channel not found"),
                ("Channel ID", str(config.GIVEAWAY_CHANNEL_ID)),
            ], emoji="⚠️")

        # Start background task
        self._running = True
        self._check_task = asyncio.create_task(self._check_expired_loop())

        # Count active giveaways
        active = db.get_active_giveaways()

        log.tree("Giveaway Service Ready", [
            ("Channel ID", str(config.GIVEAWAY_CHANNEL_ID)),
            ("Active Giveaways", str(len(active))),
        ], emoji="🎉")

    async def _check_member_eligible(
        self,
        member: Optional[discord.Member],
        giveaway: Dict[str, Any],
    ) -> bool:
        """
        Check if a member still meets giveaway requirements.

        Used at winner selection to re-validate eligibility since
        users may lose required roles or level between entry and end time.

        Args:
            member: Discord member to check (None if left server)
            giveaway: Giveaway data dict

        Returns:
            True if eligible, False otherwise
        """
        # User left server
        if not member:
            return False

        # Check required role
        if giveaway["required_role_id"]:
            role = member.guild.get_role(giveaway["required_role_id"])
            if role and role not in member.roles:
                return False

        # Check min level
        if giveaway["min_level"] > 0:
            user_data = await asyncio.to_thread(
                db.get_user_xp, member.id, member.guild.id
            )
            user_level = user_data.get("level", 0) if user_data else 0
            if user_level < giveaway["min_level"]:
                return False

        return True

    async def _check_expired_loop(self) -> None:
        """Background task to check for expired giveaways."""
        await self.bot.wait_until_ready()

        while self._running:
            try:
                await self._process_expired_giveaways()
            except Exception as e:
                log.tree("Giveaway Check Error", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")

            await asyncio.sleep(CHECK_INTERVAL)

    async def _process_expired_giveaways(self) -> None:
        """Process all expired giveaways."""
        expired = await asyncio.to_thread(db.get_expired_giveaways)

        for giveaway in expired:
            try:
                await self.end_giveaway(giveaway["id"])
            except Exception as e:
                log.tree("Giveaway End Error", [
                    ("ID", str(giveaway["id"])),
                    ("Error", str(e)[:50]),
                ], emoji="❌")

    async def create_giveaway(
        self,
        host: discord.Member,
        prize_type: str,
        prize_description: str,
        prize_amount: int,
        prize_coins: int,
        prize_role_id: Optional[int],
        required_role_id: Optional[int],
        min_level: int,
        winner_count: int,
        duration: timedelta,
        ping_role: bool = False
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Create and start a new giveaway.

        Returns:
            Tuple of (success, message, giveaway_id)
        """
        # Validate prize amounts are non-negative
        if prize_amount < 0:
            log.tree("Giveaway Create Failed", [
                ("Host", f"{host.name} ({host.id})"),
                ("Reason", f"Invalid prize_amount: {prize_amount}"),
            ], emoji="❌")
            return False, "Prize amount cannot be negative", None

        if prize_coins < 0:
            log.tree("Giveaway Create Failed", [
                ("Host", f"{host.name} ({host.id})"),
                ("Reason", f"Invalid prize_coins: {prize_coins}"),
            ], emoji="❌")
            return False, "Prize coins cannot be negative", None

        if winner_count < 1:
            log.tree("Giveaway Create Failed", [
                ("Host", f"{host.name} ({host.id})"),
                ("Reason", f"Invalid winner_count: {winner_count}"),
            ], emoji="❌")
            return False, "Winner count must be at least 1", None

        channel = self.bot.get_channel(config.GIVEAWAY_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            log.tree("Giveaway Create Failed", [
                ("Host", f"{host.name} ({host.id})"),
                ("Reason", "Giveaway channel not found"),
            ], emoji="❌")
            return False, "Giveaway channel not found", None

        ends_at = datetime.now(TIMEZONE) + duration

        # Build requirements text
        requirements = []
        if required_role_id:
            role = host.guild.get_role(required_role_id)
            if role:
                requirements.append(f"• Must have {role.mention}")
        if min_level > 0:
            requirements.append(f"• Level {min_level}+")

        req_text = "\n".join(requirements) if requirements else "• None"

        # Build embed
        embed = discord.Embed(
            title="🎉 GIVEAWAY 🎉",
            color=COLOR_SYRIA_GREEN,
        )
        embed.add_field(
            name="Prize",
            value=f"**{prize_description}**",
            inline=False
        )
        embed.add_field(
            name="Winners",
            value=f"`{winner_count}`",
            inline=True
        )
        embed.add_field(
            name="Ends",
            value=f"<t:{int(ends_at.timestamp())}:R>",
            inline=True
        )
        embed.add_field(
            name="Requirements",
            value=req_text,
            inline=False
        )
        embed.add_field(
            name="Bonus",
            value=f"<@&{config.BOOSTER_ROLE_ID}> get **{BOOSTER_MULTIPLIER}x** entries!",
            inline=False
        )

        # Add giveaway emoji as thumbnail
        embed.set_thumbnail(url=GIVEAWAY_EMOJI_URL)

        # Add giveaway image
        if GIVEAWAY_IMAGE_PATH.exists():
            embed.set_image(url="attachment://giveaway.gif")

        set_footer(embed)

        try:
            # Ping giveaway role in same message if enabled
            content = f"<@&{config.GIVEAWAY_ROLE_ID}>" if ping_role and config.GIVEAWAY_ROLE_ID else None

            # Prepare file for embed image
            file = discord.File(GIVEAWAY_IMAGE_PATH, filename="giveaway.gif") if GIVEAWAY_IMAGE_PATH.exists() else None

            msg = await channel.send(content=content, embed=embed, file=file)

            # Add reaction for entry
            try:
                await msg.add_reaction(EMOJI_GIVEAWAY)
            except discord.HTTPException as e:
                log.tree("Giveaway Reaction Failed", [
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

            # Save to database
            giveaway_id = await asyncio.to_thread(
                db.create_giveaway,
                msg.id,
                channel.id,
                host.id,
                prize_type,
                prize_description,
                prize_amount,
                prize_coins,
                prize_role_id,
                required_role_id,
                min_level,
                winner_count,
                ends_at
            )

            if not giveaway_id:
                await msg.delete()
                log.tree("Giveaway Create Failed", [
                    ("Host", f"{host.name} ({host.id})"),
                    ("Reason", "Database save failed"),
                ], emoji="❌")
                return False, "Failed to save giveaway", None

            # Send notification to notification channel
            await self._send_notification(
                msg=msg,
                prize_description=prize_description,
                winner_count=winner_count,
                ends_at=ends_at,
                required_role_id=required_role_id,
                min_level=min_level,
                host=host,
            )

            log.tree("Giveaway Started", [
                ("ID", str(giveaway_id)),
                ("Host", f"{host.name} ({host.id})"),
                ("Prize", prize_description[:30]),
                ("Type", prize_type),
                ("Winners", str(winner_count)),
                ("Duration", str(duration)),
                ("Requirements", f"Role: {required_role_id}, Level: {min_level}"),
                ("Ping", "Yes" if ping_role else "No"),
            ], emoji="🎉")

            return True, f"Giveaway started! ID: {giveaway_id}", giveaway_id

        except discord.Forbidden:
            log.tree("Giveaway Create Forbidden", [
                ("Host", f"{host.name} ({host.id})"),
                ("Reason", "Missing permissions"),
            ], emoji="🔒")
            return False, "Missing permissions to send in giveaway channel", None
        except Exception as e:
            log.tree("Giveaway Create Error", [
                ("Host", f"{host.name} ({host.id})"),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False, f"Error: {str(e)[:50]}", None

    async def _send_notification(
        self,
        msg: discord.Message,
        prize_description: str,
        winner_count: int,
        ends_at: datetime,
        required_role_id: Optional[int],
        min_level: int,
        host: discord.Member,
    ) -> None:
        """Send giveaway notification to general channel."""
        channel_id = config.GENERAL_CHANNEL_ID
        if not channel_id:
            log.tree("Giveaway Notification Skipped", [
                ("Reason", "No notification or general channel configured"),
            ], emoji="ℹ️")
            return

        notify_channel = self.bot.get_channel(channel_id)
        if not notify_channel:
            log.tree("Giveaway Notification Skipped", [
                ("Reason", "Notification channel not found"),
            ], emoji="⚠️")
            return

        try:
            # Build requirements text
            requirements = []
            if required_role_id:
                role = host.guild.get_role(required_role_id)
                if role:
                    requirements.append(f"{role.mention}")
            if min_level > 0:
                requirements.append(f"Level `{min_level}+`")
            req_text = " • ".join(requirements) if requirements else "`None`"

            # Build notification embed
            embed = discord.Embed(
                title="🎉 New Giveaway!",
                description=f"**{prize_description}**",
                color=COLOR_SYRIA_GREEN,
            )
            embed.add_field(
                name="Winners",
                value=f"`{winner_count}`",
                inline=True
            )
            embed.add_field(
                name="Ends",
                value=f"<t:{int(ends_at.timestamp())}:R>",
                inline=True
            )
            embed.add_field(
                name="Requirements",
                value=req_text,
                inline=True
            )

            # Add giveaway emoji as thumbnail
            embed.set_thumbnail(url=GIVEAWAY_EMOJI_URL)

            set_footer(embed)

            # Create view with link button
            giveaway_url = f"https://discord.com/channels/{msg.guild.id}/{msg.channel.id}/{msg.id}"

            from src.services.giveaway.views import GiveawayNotificationView
            view = GiveawayNotificationView(giveaway_url)

            await notify_channel.send(embed=embed, view=view)

            log.tree("Giveaway Notification Sent", [
                ("Channel", notify_channel.name),
                ("Prize", prize_description[:30]),
            ], emoji="📢")

        except Exception as e:
            log.tree("Giveaway Notification Failed", [
                ("Error", str(e)[:50]),
            ], emoji="❌")

    async def enter_giveaway(
        self,
        giveaway_id: int,
        user: discord.Member
    ) -> Tuple[bool, str]:
        """
        Enter a user into a giveaway.

        Returns:
            Tuple of (success, message)
        """
        giveaway = await asyncio.to_thread(db.get_giveaway, giveaway_id)

        if not giveaway:
            log.tree("Giveaway Entry Failed", [
                ("User", f"{user.name} ({user.id})"),
                ("Giveaway ID", str(giveaway_id)),
                ("Reason", "Giveaway not found"),
            ], emoji="⚠️")
            return False, "Giveaway not found"

        if giveaway["ended"]:
            log.tree("Giveaway Entry Failed", [
                ("User", f"{user.name} ({user.id})"),
                ("Giveaway ID", str(giveaway_id)),
                ("Reason", "Giveaway has ended"),
            ], emoji="⚠️")
            return False, "This giveaway has ended"

        # Block moderators from entering
        if config.MOD_ROLE_ID:
            mod_role = user.guild.get_role(config.MOD_ROLE_ID)
            if mod_role and mod_role in user.roles:
                log.tree("Giveaway Entry Denied", [
                    ("User", f"{user.name} ({user.id})"),
                    ("Giveaway ID", str(giveaway_id)),
                    ("Reason", "Moderator"),
                ], emoji="🚫")
                return False, "Moderators cannot enter giveaways"

        # Check requirements
        if giveaway["required_role_id"]:
            role = user.guild.get_role(giveaway["required_role_id"])
            if role and role not in user.roles:
                log.tree("Giveaway Entry Denied", [
                    ("User", f"{user.name} ({user.id})"),
                    ("Giveaway ID", str(giveaway_id)),
                    ("Reason", f"Missing role: {role.name}"),
                ], emoji="🚫")
                return False, f"You need the **{role.name}** role to enter"

        if giveaway["min_level"] > 0:
            user_data = await asyncio.to_thread(
                db.get_user_xp, user.id, user.guild.id
            )
            user_level = user_data.get("level", 0) if user_data else 0
            if user_level < giveaway["min_level"]:
                log.tree("Giveaway Entry Denied", [
                    ("User", f"{user.name} ({user.id})"),
                    ("Giveaway ID", str(giveaway_id)),
                    ("Reason", f"Level {user_level} < {giveaway['min_level']}"),
                ], emoji="🚫")
                return False, f"You need to be level **{giveaway['min_level']}+** to enter (you're level {user_level})"

        # Check if already entered
        already_entered = await asyncio.to_thread(
            db.has_entered_giveaway, giveaway_id, user.id
        )
        if already_entered:
            log.tree("Giveaway Entry Failed", [
                ("User", f"{user.name} ({user.id})"),
                ("Giveaway ID", str(giveaway_id)),
                ("Reason", "Already entered"),
            ], emoji="ℹ️")
            return False, "You've already entered this giveaway"

        # Add entry
        success = await asyncio.to_thread(
            db.add_giveaway_entry, giveaway_id, user.id
        )

        if success:

            # Check if booster for bonus message
            is_booster = False
            if config.BOOSTER_ROLE_ID:
                booster_role = user.guild.get_role(config.BOOSTER_ROLE_ID)
                is_booster = booster_role and booster_role in user.roles

            log.tree("Giveaway Entry Success", [
                ("User", f"{user.name} ({user.id})"),
                ("Giveaway ID", str(giveaway_id)),
                ("Booster", "Yes" if is_booster else "No"),
            ], emoji="🎟️")

            if is_booster:
                return True, f"You've entered with **{BOOSTER_MULTIPLIER}x entries**! (Booster bonus) Good luck! 🍀"
            return True, "You've entered the giveaway! Good luck! 🍀"
        else:
            log.tree("Giveaway Entry Failed", [
                ("User", f"{user.name} ({user.id})"),
                ("Giveaway ID", str(giveaway_id)),
                ("Reason", "Database error"),
            ], emoji="❌")
            return False, "Failed to enter giveaway"

    async def leave_giveaway(
        self,
        giveaway_id: int,
        user: discord.Member
    ) -> Tuple[bool, str]:
        """Remove user from giveaway."""
        giveaway = await asyncio.to_thread(db.get_giveaway, giveaway_id)

        if not giveaway:
            log.tree("Giveaway Leave Failed", [
                ("User", f"{user.name} ({user.id})"),
                ("Giveaway ID", str(giveaway_id)),
                ("Reason", "Giveaway not found"),
            ], emoji="⚠️")
            return False, "Giveaway not found"

        if giveaway["ended"]:
            log.tree("Giveaway Leave Failed", [
                ("User", f"{user.name} ({user.id})"),
                ("Giveaway ID", str(giveaway_id)),
                ("Reason", "Giveaway has ended"),
            ], emoji="⚠️")
            return False, "Giveaway has ended"

        success = await asyncio.to_thread(
            db.remove_giveaway_entry, giveaway_id, user.id
        )

        if success:
            log.tree("Giveaway Entry Withdrawn", [
                ("User", f"{user.name} ({user.id})"),
                ("Giveaway ID", str(giveaway_id)),
            ], emoji="🎟️")
            return True, "You've left the giveaway"
        else:
            log.tree("Giveaway Leave Failed", [
                ("User", f"{user.name} ({user.id})"),
                ("Giveaway ID", str(giveaway_id)),
                ("Reason", "Not entered"),
            ], emoji="ℹ️")
            return False, "You weren't entered in this giveaway"

    async def _update_entry_count(self, giveaway: Dict[str, Any]) -> None:
        """Update the entry count on the giveaway embed."""
        try:
            channel = self.bot.get_channel(giveaway["channel_id"])
            if not channel:
                log.tree("Giveaway Entry Count Update Skipped", [
                    ("Giveaway ID", str(giveaway["id"])),
                    ("Reason", "Channel not found"),
                ], emoji="⚠️")
                return

            msg = await channel.fetch_message(giveaway["message_id"])
            if not msg or not msg.embeds:
                log.tree("Giveaway Entry Count Update Skipped", [
                    ("Giveaway ID", str(giveaway["id"])),
                    ("Reason", "Message or embed not found"),
                ], emoji="⚠️")
                return

            entry_count = await asyncio.to_thread(
                db.get_giveaway_entry_count, giveaway["id"]
            )

            embed = msg.embeds[0]
            # Find and update the Entries field
            for i, field in enumerate(embed.fields):
                if field.name == "Entries":
                    embed.set_field_at(i, name="Entries", value=f"`{entry_count}`", inline=True)
                    break

            await msg.edit(embed=embed)
        except Exception as e:
            log.tree("Giveaway Entry Count Update Failed", [
                ("Giveaway ID", str(giveaway["id"])),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    async def end_giveaway(
        self,
        giveaway_id: int,
        reroll: bool = False
    ) -> Tuple[bool, str, List[int]]:
        """
        End a giveaway and pick winners.

        Returns:
            Tuple of (success, message, winner_ids)
        """
        giveaway = await asyncio.to_thread(db.get_giveaway, giveaway_id)

        if not giveaway:
            log.tree("Giveaway End Failed", [
                ("ID", str(giveaway_id)),
                ("Reason", "Not found"),
            ], emoji="⚠️")
            return False, "Giveaway not found", []

        if giveaway["ended"] and not reroll:
            log.tree("Giveaway End Skipped", [
                ("ID", str(giveaway_id)),
                ("Reason", "Already ended"),
            ], emoji="ℹ️")
            return False, "Giveaway already ended", []

        # Get entries
        entries = await asyncio.to_thread(db.get_giveaway_entries, giveaway_id)

        if not entries:
            # No entries - mark as ended
            await asyncio.to_thread(db.end_giveaway, giveaway_id, [])
            await self._update_giveaway_embed_ended(giveaway, [])
            log.tree("Giveaway Ended (No Entries)", [
                ("ID", str(giveaway_id)),
            ], emoji="🎉")
            return True, "Giveaway ended with no entries", []

        # Build weighted entry pool (boosters get multiple entries)
        # Re-validate eligibility at end time (users may have lost role/level)
        guild = self.bot.get_guild(config.GUILD_ID)
        booster_role = None
        if guild and config.BOOSTER_ROLE_ID:
            booster_role = guild.get_role(config.BOOSTER_ROLE_ID)

        weighted_entries = []
        booster_count = 0
        ineligible_count = 0

        for user_id in entries:
            member = guild.get_member(user_id) if guild else None

            # Re-validate eligibility at end time
            if not await self._check_member_eligible(member, giveaway):
                ineligible_count += 1
                continue

            # Check if user is a booster
            is_booster = False
            if member and booster_role and booster_role in member.roles:
                is_booster = True
                booster_count += 1

            # Add entries (boosters get BOOSTER_MULTIPLIER entries)
            if is_booster:
                weighted_entries.extend([user_id] * BOOSTER_MULTIPLIER)
            else:
                weighted_entries.append(user_id)

        # Get unique eligible users for winner count calculation
        eligible_users = list(set(weighted_entries))

        if not eligible_users:
            # All entries became ineligible
            await asyncio.to_thread(db.end_giveaway, giveaway_id, [])
            await self._update_giveaway_embed_ended(giveaway, [])
            log.tree("Giveaway Ended (No Eligible Entries)", [
                ("ID", str(giveaway_id)),
                ("Original Entries", str(len(entries))),
                ("Ineligible", str(ineligible_count)),
            ], emoji="⚠️")
            return True, "Giveaway ended with no eligible entries", []

        log.tree("Giveaway Winner Selection", [
            ("ID", str(giveaway_id)),
            ("Total Entries", str(len(entries))),
            ("Eligible", str(len(eligible_users))),
            ("Ineligible", str(ineligible_count)),
            ("Boosters", str(booster_count)),
            ("Weighted Pool", str(len(weighted_entries))),
        ], emoji="🎲")

        # Pick winners (unique - no duplicates)
        winner_count = min(giveaway["winner_count"], len(eligible_users))
        winners = []
        pool = weighted_entries.copy()

        while len(winners) < winner_count and pool:
            winner = random.choice(pool)
            if winner not in winners:
                winners.append(winner)
            # Remove all instances of this winner from pool
            pool = [u for u in pool if u != winner]

        # Save winners
        await asyncio.to_thread(db.end_giveaway, giveaway_id, winners)

        # Update embed
        await self._update_giveaway_embed_ended(giveaway, winners)

        # Grant prizes
        await self._grant_prizes(giveaway, winners)

        # Announce winners
        await self._announce_winners(giveaway, winners)

        log.tree("Giveaway Ended", [
            ("ID", str(giveaway_id)),
            ("Prize", giveaway["prize_description"][:30]),
            ("Entries", str(len(entries))),
            ("Winners", ", ".join(str(w) for w in winners)),
        ], emoji="🏆")

        return True, f"Giveaway ended! {len(winners)} winner(s) selected", winners

    async def _update_giveaway_embed_ended(
        self,
        giveaway: Dict[str, Any],
        winners: List[int]
    ) -> None:
        """Update giveaway embed to show ended state."""
        try:
            channel = self.bot.get_channel(giveaway["channel_id"])
            if not channel:
                log.tree("Giveaway Embed Update Skipped", [
                    ("ID", str(giveaway["id"])),
                    ("Reason", "Channel not found"),
                ], emoji="⚠️")
                return

            msg = await channel.fetch_message(giveaway["message_id"])
            if not msg:
                log.tree("Giveaway Embed Update Skipped", [
                    ("ID", str(giveaway["id"])),
                    ("Reason", "Message not found"),
                ], emoji="⚠️")
                return

            # Build winners text
            if winners:
                winner_mentions = [f"<@{w}>" for w in winners]
                winners_text = "\n".join(winner_mentions)
            else:
                winners_text = "No entries"

            embed = discord.Embed(
                title="🎉 GIVEAWAY ENDED 🎉",
                color=COLOR_SUCCESS,
            )
            embed.add_field(
                name="Prize",
                value=f"**{giveaway['prize_description']}**",
                inline=False
            )
            embed.add_field(
                name="Winners",
                value=winners_text,
                inline=False
            )

            entry_count = await asyncio.to_thread(
                db.get_giveaway_entry_count, giveaway["id"]
            )
            embed.add_field(
                name="Total Entries",
                value=f"`{entry_count}`",
                inline=True
            )
            set_footer(embed)

            # Remove buttons
            await msg.edit(embed=embed, view=None)

        except Exception as e:
            log.tree("Giveaway Embed Update Failed", [
                ("ID", str(giveaway["id"])),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    async def _grant_prizes(
        self,
        giveaway: Dict[str, Any],
        winners: List[int]
    ) -> None:
        """Grant prizes to winners."""
        prize_type = giveaway["prize_type"]
        prize_amount = giveaway["prize_amount"]
        guild = self.bot.get_guild(config.GUILD_ID)

        if not guild:
            log.tree("Giveaway Prize Grant Skipped", [
                ("Giveaway ID", str(giveaway["id"])),
                ("Reason", "Guild not found"),
            ], emoji="⚠️")
            return

        for winner_id in winners:
            member = guild.get_member(winner_id)
            if not member:
                log.tree("Giveaway Prize Grant Skipped", [
                    ("Winner ID", str(winner_id)),
                    ("Giveaway ID", str(giveaway["id"])),
                    ("Reason", "Member not found in guild"),
                ], emoji="⚠️")
                continue

            try:
                if prize_type == "xp" and self.bot.xp_service:
                    await self.bot.xp_service.grant_xp(
                        member, prize_amount, "giveaway"
                    )
                    log.tree("Giveaway Prize Granted (XP)", [
                        ("Winner", f"{member.name} ({member.id})"),
                        ("Amount", f"{prize_amount:,} XP"),
                    ], emoji="⭐")

                elif prize_type == "coins" and self.bot.currency_service:
                    success, msg = await self.bot.currency_service.grant(
                        user_id=winner_id,
                        amount=prize_amount,
                        reason=f"Giveaway win: {giveaway['prize_description'][:30]}",
                        target="bank"
                    )
                    if success:
                        log.tree("Giveaway Prize Granted (Coins)", [
                            ("Winner", f"{member.name} ({member.id})"),
                            ("Amount", f"{prize_amount:,} coins"),
                        ], emoji="💰")
                    else:
                        log.tree("Giveaway Prize Grant Failed (Coins)", [
                            ("Winner", f"{member.name} ({member.id})"),
                            ("Amount", f"{prize_amount:,} coins"),
                            ("Reason", msg[:50]),
                        ], emoji="❌")

                elif prize_type == "combo":
                    # Grant both XP and coins
                    prize_coins = giveaway.get("prize_coins", 0)

                    if self.bot.xp_service and prize_amount > 0:
                        await self.bot.xp_service.grant_xp(
                            member, prize_amount, "giveaway"
                        )

                    if self.bot.currency_service and prize_coins > 0:
                        await self.bot.currency_service.grant(
                            user_id=winner_id,
                            amount=prize_coins,
                            reason=f"Giveaway win: {giveaway['prize_description'][:30]}",
                            target="bank"
                        )

                    log.tree("Giveaway Prize Granted (Combo)", [
                        ("Winner", f"{member.name} ({member.id})"),
                        ("XP", f"{prize_amount:,}"),
                        ("Coins", f"{prize_coins:,}"),
                    ], emoji="✨")

                elif prize_type == "role" and giveaway["prize_role_id"]:
                    role = guild.get_role(giveaway["prize_role_id"])
                    if role and role not in member.roles:
                        await member.add_roles(role, reason="Giveaway prize")
                        log.tree("Giveaway Prize Granted (Role)", [
                            ("Winner", f"{member.name} ({member.id})"),
                            ("Role", role.name),
                        ], emoji="🏷️")
                    elif role and role in member.roles:
                        log.tree("Giveaway Prize Skipped (Role)", [
                            ("Winner", f"{member.name} ({member.id})"),
                            ("Reason", "Already has role"),
                        ], emoji="ℹ️")

                elif prize_type in ("nitro", "custom"):
                    # Manual prizes - just announced
                    log.tree("Giveaway Prize Pending (Manual)", [
                        ("Winner", f"{member.name} ({member.id})"),
                        ("Prize Type", prize_type),
                        ("Prize", giveaway["prize_description"][:30]),
                    ], emoji="📋")
            except Exception as e:
                log.tree("Giveaway Prize Grant Failed", [
                    ("Winner", f"{member.name} ({member.id})"),
                    ("Prize Type", prize_type),
                    ("Error", str(e)[:50]),
                ], emoji="❌")

    async def _announce_winners(
        self,
        giveaway: Dict[str, Any],
        winners: List[int]
    ) -> None:
        """Announce winners in the giveaway channel and general chat."""
        guild = self.bot.get_guild(config.GUILD_ID)

        try:
            channel = self.bot.get_channel(giveaway["channel_id"])
            if not channel:
                log.tree("Giveaway Announcement Skipped", [
                    ("ID", str(giveaway["id"])),
                    ("Reason", "Giveaway channel not found"),
                ], emoji="⚠️")
                return

            if not winners:
                await channel.send(
                    f"🎉 The giveaway for **{giveaway['prize_description']}** ended with no entries!"
                )
                log.tree("Giveaway Announcement Sent (No Winners)", [
                    ("ID", str(giveaway["id"])),
                    ("Prize", giveaway["prize_description"][:30]),
                ], emoji="📢")
                return

            winner_mentions = " ".join(f"<@{w}>" for w in winners)

            # Send announcement in giveaway channel with moderator note
            await channel.send(
                f"🎉 Congratulations {winner_mentions}! "
                f"You won **{giveaway['prize_description']}**!\n"
                f"-# A moderator will contact you soon to deliver your prize."
            )

            log.tree("Giveaway Announcement Sent", [
                ("ID", str(giveaway["id"])),
                ("Channel", channel.name),
                ("Winners", str(len(winners))),
            ], emoji="📢")

            # Send notification to general chat
            general_channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
            if not general_channel:
                log.tree("Giveaway Winner Notification Skipped", [
                    ("Reason", "General channel not found"),
                ], emoji="ℹ️")
                return
            if not guild:
                log.tree("Giveaway Winner Notification Skipped", [
                    ("Reason", "Guild not found"),
                ], emoji="ℹ️")
                return

            if general_channel and guild:
                # Get first winner for thumbnail
                first_winner = guild.get_member(winners[0])

                embed = discord.Embed(
                    title="🎉 Giveaway Winner!",
                    description=f"Congratulations {winner_mentions}!\n\nYou won **{giveaway['prize_description']}**!",
                    color=COLOR_SUCCESS,
                )

                if first_winner:
                    embed.set_thumbnail(url=first_winner.display_avatar.url)

                set_footer(embed)

                await general_channel.send(embed=embed)

                log.tree("Giveaway Winner Notification Sent", [
                    ("Channel", general_channel.name),
                    ("Winners", winner_mentions[:50]),
                ], emoji="📢")

        except Exception as e:
            log.tree("Giveaway Announcement Failed", [
                ("ID", str(giveaway["id"])),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    async def cancel_giveaway(self, giveaway_id: int) -> Tuple[bool, str]:
        """Cancel a giveaway."""
        giveaway = await asyncio.to_thread(db.get_giveaway, giveaway_id)

        if not giveaway:
            log.tree("Giveaway Cancel Failed", [
                ("ID", str(giveaway_id)),
                ("Reason", "Not found"),
            ], emoji="⚠️")
            return False, "Giveaway not found"

        if giveaway["ended"]:
            log.tree("Giveaway Cancel Failed", [
                ("ID", str(giveaway_id)),
                ("Reason", "Already ended"),
            ], emoji="⚠️")
            return False, "Giveaway already ended"

        # Delete message
        try:
            channel = self.bot.get_channel(giveaway["channel_id"])
            if channel:
                msg = await channel.fetch_message(giveaway["message_id"])
                if msg:
                    await msg.delete()
        except Exception as e:
            log.tree("Giveaway Message Delete Failed", [
                ("ID", str(giveaway_id)),
                ("Reason", str(e)[:50]),
            ], emoji="⚠️")

        # Delete from database
        await asyncio.to_thread(db.cancel_giveaway, giveaway_id)

        log.tree("Giveaway Cancelled", [
            ("ID", str(giveaway_id)),
        ], emoji="🗑️")

        return True, "Giveaway cancelled"

    async def reroll_giveaway(self, giveaway_id: int) -> Tuple[bool, str, List[int]]:
        """Reroll winners for an ended giveaway."""
        giveaway = await asyncio.to_thread(db.get_giveaway, giveaway_id)

        if not giveaway:
            log.tree("Giveaway Reroll Failed", [
                ("ID", str(giveaway_id)),
                ("Reason", "Not found"),
            ], emoji="⚠️")
            return False, "Giveaway not found", []

        if not giveaway["ended"]:
            log.tree("Giveaway Reroll Failed", [
                ("ID", str(giveaway_id)),
                ("Reason", "Not ended yet"),
            ], emoji="⚠️")
            return False, "Giveaway hasn't ended yet", []

        return await self.end_giveaway(giveaway_id, reroll=True)

    def stop(self) -> None:
        """Stop the giveaway service."""
        self._running = False
        if self._check_task:
            self._check_task.cancel()

        log.tree("Giveaway Service Stopped", [], emoji="🛑")
