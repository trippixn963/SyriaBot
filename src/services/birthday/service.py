"""
SyriaBot - Birthday Service
===========================

Birthday tracking with automatic role assignment on birthdays.

Features:
- Users can set/remove their birthday via `/birthday` command
- Daily check at midnight (EST) for birthdays
- Birthday role granted for 24 hours
- Announcement in configured channel
- DM with rewards: 3x XP and 100k coins to bank

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import calendar
import time
from datetime import datetime, time as dt_time
from typing import TYPE_CHECKING, Optional, Tuple, Set
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks

from src.core.config import config
from src.core.colors import COLOR_SYRIA_GREEN
from src.core.logger import logger
from src.services.database import db
from src.utils.footer import set_footer

if TYPE_CHECKING:
    from src.bot import SyriaBot


# Timezone for birthday checks
NY_TZ = ZoneInfo("America/New_York")

# Birthday role duration (24 hours in seconds)
BIRTHDAY_ROLE_DURATION = 24 * 60 * 60

# Birthday rewards
BIRTHDAY_COINS = 100_000
BIRTHDAY_XP_MULTIPLIER = 3.0

# Track users with active birthday bonus (for 3x XP)
_birthday_bonus_users: Set[int] = set()
_birthday_bonus_lock = asyncio.Lock()

# Month names for display
MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


class BirthdayService:
    """
    Service for birthday tracking and role management.

    DESIGN:
        Users set their birthday once via /birthday set.
        Daily check at 5:00 AM EST grants birthday role for 24 hours.
        Birthday users get 3x XP and coin rewards via DM.
    """

    def __init__(self, bot: "SyriaBot") -> None:
        """
        Initialize the birthday service.

        Args:
            bot: Main bot instance for Discord API access.
        """
        self.bot = bot
        self._birthday_role_id: Optional[int] = None
        self._announcement_channel_id: Optional[int] = None
        self._enabled = False

    async def setup(self) -> None:
        """
        Initialize and start the birthday service.

        Validates configuration, starts the daily birthday check task,
        starts the hourly role expiry check, and restores any active
        birthday bonuses from a previous session.
        """
        # Get config - role ID is required, channel is optional
        self._birthday_role_id = config.BIRTHDAY_ROLE_ID
        self._announcement_channel_id = config.BIRTHDAY_ANNOUNCE_CHANNEL_ID

        if not self._birthday_role_id:
            logger.tree("Birthday Service", [
                ("Status", "Disabled"),
                ("Reason", "BIRTHDAY_ROLE_ID not configured"),
            ], emoji="ℹ️")
            return

        self._enabled = True

        # Start the daily birthday check
        self.birthday_check.start()

        # Start role expiry check (runs every hour)
        self.role_expiry_check.start()

        # Get birthday count for log
        count = await asyncio.to_thread(db.get_birthday_count, config.GUILD_ID)

        # Restore active birthday bonus users (in case of restart during birthday)
        active_birthday_users = await asyncio.to_thread(
            db.get_active_birthday_roles, config.GUILD_ID
        )
        async with _birthday_bonus_lock:
            for user_id in active_birthday_users:
                _birthday_bonus_users.add(user_id)

        logger.tree("Birthday Service Ready", [
            ("Role ID", str(self._birthday_role_id)),
            ("Announce Channel", str(self._announcement_channel_id) if self._announcement_channel_id else "None"),
            ("Registered Birthdays", str(count)),
            ("Active Birthday Bonuses", str(len(_birthday_bonus_users))),
            ("Daily Check", "5:00 AM EST"),
        ], emoji="🎂")

    def stop(self) -> None:
        """Stop the birthday service."""
        if self.birthday_check.is_running():
            self.birthday_check.cancel()
        if self.role_expiry_check.is_running():
            self.role_expiry_check.cancel()
        logger.tree("Birthday Service Stopped", [], emoji="🛑")

    # =========================================================================
    # Scheduled Tasks
    # =========================================================================

    @tasks.loop(time=dt_time(hour=10, minute=0))  # 10:00 UTC = 5:00 AM EST
    async def birthday_check(self) -> None:
        """Daily birthday check - grant birthday roles."""
        if not self._enabled:
            return

        now = datetime.now(NY_TZ)
        month = now.month
        day = now.day

        logger.tree("Birthday Check Starting", [
            ("Date", f"{MONTH_NAMES[month]} {day}"),
            ("Time", now.strftime("%I:%M %p EST")),
        ], emoji="🎂")

        # Get today's birthdays
        birthday_user_ids = await asyncio.to_thread(
            db.get_todays_birthdays, config.GUILD_ID, month, day
        )

        if not birthday_user_ids:
            logger.tree("Birthday Check Complete", [
                ("Birthdays Today", "0"),
            ], emoji="🎂")
            return

        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            logger.tree("Birthday Check Failed", [
                ("Reason", "Guild not found"),
            ], emoji="⚠️")
            return

        role = guild.get_role(self._birthday_role_id)
        if not role:
            logger.tree("Birthday Check Failed", [
                ("Reason", "Birthday role not found"),
                ("Role ID", str(self._birthday_role_id)),
            ], emoji="⚠️")
            return

        granted_count = 0
        current_year = now.year

        for user_id in birthday_user_ids:
            member = guild.get_member(user_id)
            if not member:
                continue

            # Skip if already has the role (prevents double rewards)
            if role in member.roles:
                logger.tree("Birthday Role Skipped", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("Reason", "Already has role"),
                ], emoji="ℹ️")
                continue

            # Skip if already has bonus (extra safeguard against abuse)
            async with _birthday_bonus_lock:
                has_bonus = user_id in _birthday_bonus_users
            if has_bonus:
                logger.tree("Birthday Bonus Skipped", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("Reason", "Already has 3x XP bonus"),
                ], emoji="⚠️")
                continue

            # Get birthday data for age calculation
            birthday_data = await asyncio.to_thread(
                db.get_birthday, user_id, config.GUILD_ID
            )
            age = None
            if birthday_data and birthday_data.get("birth_year"):
                age = current_year - birthday_data["birth_year"]

            try:
                await member.add_roles(role, reason="Birthday!")
                await asyncio.to_thread(
                    db.set_birthday_role_granted, user_id, config.GUILD_ID, int(time.time())
                )
                granted_count += 1

                # Add to birthday bonus users (for 3x XP)
                async with _birthday_bonus_lock:
                    _birthday_bonus_users.add(user_id)

                logger.tree("Birthday Role Granted", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(user_id)),
                    ("Birthday", f"{MONTH_NAMES[month]} {day}"),
                    ("Age", str(age) if age else "Unknown"),
                    ("Rewards", "3x XP + 100k coins"),
                ], emoji="🎂")

                # Send announcement
                await self._announce_birthday(member, age)

                # DM user with rewards and grant coins
                await self._send_birthday_rewards(member, age)

            except discord.Forbidden:
                logger.tree("Birthday Role Grant Failed", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("Reason", "Missing permissions"),
                ], emoji="⚠️")
            except discord.HTTPException as e:
                logger.tree("Birthday Role Grant Failed", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        logger.tree("Birthday Check Complete", [
            ("Birthdays Today", str(len(birthday_user_ids))),
            ("Roles Granted", str(granted_count)),
        ], emoji="🎂")

    @tasks.loop(hours=1)
    async def role_expiry_check(self) -> None:
        """Hourly check to remove expired birthday roles (24h duration)."""
        if not self._enabled:
            return

        cutoff_time = int(time.time()) - BIRTHDAY_ROLE_DURATION

        expired_user_ids = await asyncio.to_thread(
            db.get_expired_birthday_roles, config.GUILD_ID, cutoff_time
        )

        if not expired_user_ids:
            return

        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            return

        role = guild.get_role(self._birthday_role_id)
        if not role:
            return

        removed_count = 0
        for user_id in expired_user_ids:
            member = guild.get_member(user_id)

            # Clear the granted timestamp regardless of member presence
            await asyncio.to_thread(
                db.clear_birthday_role_granted, user_id, config.GUILD_ID
            )

            # Remove from birthday bonus users (3x XP ends)
            async with _birthday_bonus_lock:
                had_bonus = user_id in _birthday_bonus_users
                _birthday_bonus_users.discard(user_id)

            if had_bonus:
                logger.tree("Birthday XP Bonus Expired", [
                    ("ID", str(user_id)),
                    ("Bonus", "3x XP ended"),
                ], emoji="⏰")

            if not member:
                continue

            if role not in member.roles:
                continue

            try:
                await member.remove_roles(role, reason="Birthday celebration ended")
                removed_count += 1

                logger.tree("Birthday Role Removed", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(user_id)),
                    ("Duration", "24 hours"),
                ], emoji="🎂")

            except discord.Forbidden:
                logger.tree("Birthday Role Remove Failed", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("Reason", "Missing permissions"),
                ], emoji="⚠️")
            except discord.HTTPException as e:
                logger.tree("Birthday Role Remove Failed", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        if removed_count > 0:
            logger.tree("Birthday Role Expiry Check", [
                ("Expired", str(len(expired_user_ids))),
                ("Removed", str(removed_count)),
            ], emoji="🎂")

    @birthday_check.before_loop
    async def before_birthday_check(self) -> None:
        """Wait for bot to be ready before starting birthday check."""
        await self.bot.wait_until_ready()

    @role_expiry_check.before_loop
    async def before_role_expiry_check(self) -> None:
        """Wait for bot to be ready before starting role expiry check."""
        await self.bot.wait_until_ready()

    # =========================================================================
    # Public Methods (for commands)
    # =========================================================================

    async def set_birthday(
        self,
        user: discord.Member,
        month: int,
        day: int,
        year: int
    ) -> Tuple[bool, str]:
        """
        Set a user's birthday.

        Args:
            user: Discord member
            month: Birth month (1-12)
            day: Birth day (1-31)
            year: Birth year

        Returns:
            Tuple of (success, message)
        """
        # Check if user already has a birthday set (can only set once)
        existing = await asyncio.to_thread(
            db.get_birthday, user.id, user.guild.id
        )
        if existing:
            return False, f"You already have a birthday set. If you made a mistake, open a ticket in <#{config.TICKET_CHANNEL_ID}> to have it fixed."

        # Validate month
        if not 1 <= month <= 12:
            return False, "Invalid month. Please choose 1-12."

        # Validate day for the given month/year
        max_day = calendar.monthrange(year, month)[1]
        if not 1 <= day <= max_day:
            return False, f"Invalid day. {MONTH_NAMES[month]} {year} has {max_day} days."

        # Validate year (reasonable range)
        current_year = datetime.now().year
        if year < 1900 or year > current_year:
            return False, f"Invalid year. Please enter a year between 1900 and {current_year}."

        success = await asyncio.to_thread(
            db.set_birthday, user.id, user.guild.id, month, day, year
        )

        if success:
            logger.tree("Birthday Set", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Birthday", f"{MONTH_NAMES[month]} {day}, {year}"),
            ], emoji="🎂")
            return True, f"Your birthday has been set to **{MONTH_NAMES[month]} {day}, {year}**!"

        return False, "Failed to save birthday. Please try again."

    async def remove_birthday(self, user: discord.Member) -> Tuple[bool, str]:
        """
        Remove a user's birthday (Admin only).

        Args:
            user: Discord member

        Returns:
            Tuple of (success, message)
        """
        removed = await asyncio.to_thread(
            db.remove_birthday, user.id, user.guild.id
        )

        if removed:
            # Also remove any active birthday bonus
            async with _birthday_bonus_lock:
                had_bonus = user.id in _birthday_bonus_users
                _birthday_bonus_users.discard(user.id)
            if had_bonus:
                logger.tree("Birthday Bonus Revoked", [
                    ("User", f"{user.name} ({user.display_name})"),
                    ("Reason", "Birthday removed by admin"),
                ], emoji="⚠️")

            logger.tree("Birthday Removed", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
            ], emoji="🗑️")
            return True, "Birthday has been removed."

        return False, "This user doesn't have a birthday set."

    async def get_birthday(self, user: discord.Member) -> Optional[Tuple[int, int]]:
        """
        Get a user's birthday.

        Args:
            user: Discord member

        Returns:
            Tuple of (month, day) or None
        """
        data = await asyncio.to_thread(
            db.get_birthday, user.id, user.guild.id
        )
        if data:
            return (data["birth_month"], data["birth_day"])
        return None

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _announce_birthday(self, member: discord.Member, age: int = None) -> None:
        """Send birthday announcement to the configured channel."""
        if not self._announcement_channel_id:
            return

        channel = self.bot.get_channel(self._announcement_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.tree("Birthday Announce Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("Reason", "Announcement channel not found"),
            ], emoji="⚠️")
            return

        try:
            if age:
                description = (
                    f"Today is **{member.mention}**'s birthday!\n"
                    f"They're turning **{age}** years old!\n\n"
                    f"Wish them a happy birthday and help them celebrate!"
                )
            else:
                description = (
                    f"Today is **{member.mention}**'s birthday!\n\n"
                    f"Wish them a happy birthday and help them celebrate!"
                )

            embed = discord.Embed(
                title="Happy Birthday!",
                description=description,
                color=COLOR_SYRIA_GREEN
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(
                name="\u200b",
                value="*Use `/birthday set` to register your birthday!*",
                inline=False
            )
            set_footer(embed)

            await channel.send(embed=embed)

            logger.tree("Birthday Announced", [
                ("User", f"{member.name} ({member.display_name})"),
                ("Channel", channel.name),
            ], emoji="📢")

        except discord.Forbidden:
            logger.tree("Birthday Announce Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("Reason", "Missing permissions"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            logger.tree("Birthday Announce Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    async def _send_birthday_rewards(self, member: discord.Member, age: int = None) -> None:
        """DM user with birthday rewards and grant coins to bank."""
        # Grant coins to bank
        coins_granted = False
        if self.bot.currency_service and self.bot.currency_service.is_enabled():
            success, _ = await self.bot.currency_service.grant(
                user_id=member.id,
                amount=BIRTHDAY_COINS,
                reason="Birthday reward",
                target="bank"
            )
            coins_granted = success

        # Build DM message
        if age:
            greeting = f"Happy **{age}th** Birthday! 🎂🎉"
        else:
            greeting = "Happy Birthday! 🎂🎉"

        embed = discord.Embed(
            title=greeting,
            description=(
                f"The **Syria** server wishes you an amazing birthday!\n\n"
                f"As a birthday gift, you receive:\n"
                f"• **3x XP** for the next 24 hours\n"
                f"• **{BIRTHDAY_COINS:,} coins** deposited to your bank\n\n"
                f"Enjoy your special day!"
            ),
            color=COLOR_SYRIA_GREEN
        )
        embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else None)
        set_footer(embed)

        try:
            await member.send(embed=embed)
            logger.tree("Birthday DM Sent", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Coins Granted", f"{BIRTHDAY_COINS:,}" if coins_granted else "Failed"),
                ("XP Boost", "3x for 24h"),
            ], emoji="🎁")
        except discord.Forbidden:
            logger.tree("Birthday DM Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("Reason", "DMs disabled"),
                ("Coins Granted", f"{BIRTHDAY_COINS:,}" if coins_granted else "Failed"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            logger.tree("Birthday DM Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("Error", str(e)[:50]),
            ], emoji="❌")


def has_birthday_bonus(user_id: int) -> bool:
    """Check if a user has active birthday bonus (3x XP)."""
    return user_id in _birthday_bonus_users


# Singleton instance
birthday_service: Optional[BirthdayService] = None


def get_birthday_service(bot: "SyriaBot" = None) -> Optional[BirthdayService]:
    """Get or create the birthday service singleton."""
    global birthday_service
    if birthday_service is None and bot is not None:
        birthday_service = BirthdayService(bot)
    return birthday_service
