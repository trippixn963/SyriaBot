"""
SyriaBot - Service
==================

Main XP service handling message and voice XP gains.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import time
from datetime import time as dt_time
from typing import TYPE_CHECKING, Dict, Optional

import discord
from discord.ext import tasks

from src.core.config import config
from src.core.colors import COLOR_GOLD
from src.core.constants import XP_COOLDOWN_CACHE_THRESHOLD, XP_COOLDOWN_CACHE_MAX_SIZE
from src.core.logger import logger
from src.services.database import db
from src.services.birthday_service import has_birthday_bonus, BIRTHDAY_XP_MULTIPLIER
from src.utils.footer import set_footer
from .utils import level_from_xp, format_xp

if TYPE_CHECKING:
    from src.bot import SyriaBot


# Permission perks unlocked at each level (for DM notifications)
LEVEL_PERKS: Dict[int, str] = {
    1: "Connect to voice channels",
    5: "Attach files, embed links",
    10: "Use external emojis",
    20: "Use external stickers",
    30: "Change your nickname",
}


class XPService:
    """Manages XP gains from messages and voice activity."""

    def __init__(self, bot: "SyriaBot") -> None:
        """Initialize XP service with bot reference and tracking caches."""
        self.bot = bot

        # Track users in voice channels: {guild_id: {user_id: join_timestamp}}
        self._voice_sessions: Dict[int, Dict[int, float]] = {}
        self._voice_sessions_lock: asyncio.Lock = asyncio.Lock()

        # In-memory message cooldown cache: {(user_id, guild_id): timestamp}
        # Avoids DB query on every message - most will fail cooldown check
        self._message_cooldowns: Dict[tuple, int] = {}

        # Track last message content per user to prevent duplicate spam
        self._last_messages: Dict[tuple, str] = {}  # {(user_id, guild_id): content}

        # Track daily unique users to avoid duplicate DAU counts
        self._dau_cache: set = set()  # {(user_id, guild_id, date)}
        self._dau_cache_lock: asyncio.Lock = asyncio.Lock()

        # Lock for message cooldown to prevent race conditions
        self._cooldown_lock: asyncio.Lock = asyncio.Lock()

        # Track when users became muted (for anti-AFK farming)
        # {user_id: mute_start_timestamp}
        self._mute_timestamps: Dict[int, float] = {}

        # Background task for voice XP
        self._voice_xp_task: Optional[asyncio.Task] = None

        # Background task for cache cleanup
        self._cleanup_task: Optional[asyncio.Task] = None

    async def setup(self) -> None:
        """Initialize XP service."""
        # Start voice XP background task with auto-restart wrapper
        self._voice_xp_task = asyncio.create_task(self._run_with_restart(
            self._voice_xp_loop, "Voice XP Loop"
        ))

        # Start cache cleanup task (runs hourly) with auto-restart wrapper
        self._cleanup_task = asyncio.create_task(self._run_with_restart(
            self._cache_cleanup_loop, "Cache Cleanup Loop"
        ))

        # Initialize voice sessions for users already in voice (main server only)
        main_guild = self.bot.get_guild(config.GUILD_ID)
        if main_guild:
            self._voice_sessions[main_guild.id] = {}
            for vc in main_guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        self._voice_sessions[main_guild.id][member.id] = time.time()

        # Start midnight sync task
        self.midnight_role_sync.start()

        logger.tree("XP Service Started", [
            ("Message XP", f"{config.XP_MESSAGE_MIN}-{config.XP_MESSAGE_MAX}"),
            ("Voice XP", f"{config.XP_VOICE_PER_MIN}/min"),
            ("Cooldown", f"{config.XP_MESSAGE_COOLDOWN}s"),
            ("Booster Multiplier", f"{config.XP_BOOSTER_MULTIPLIER}x"),
            ("Role Rewards", str(len(config.XP_ROLE_REWARDS))),
            ("Midnight Sync", "Enabled (5:00 UTC)"),
        ], emoji="⬆️")

        # Sync active status on startup (ensures accuracy for leaderboard)
        await self._sync_active_status()

        # Sync roles on startup (fix any missed role assignments)
        await self._sync_roles()

    async def stop(self) -> None:
        """Cleanup XP service."""
        if self._voice_xp_task:
            self._voice_xp_task.cancel()
            try:
                await self._voice_xp_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Stop midnight sync task
        try:
            self.midnight_role_sync.cancel()
        except Exception:
            pass  # Task may already be stopped

        # Clear all caches on shutdown
        self._message_cooldowns.clear()
        self._last_messages.clear()
        self._mute_timestamps.clear()
        self._dau_cache.clear()
        self._voice_sessions.clear()

        logger.tree("XP Service Stopped", [
            ("Status", "All caches cleared"),
        ], emoji="🛑")

    # =========================================================================
    # Message XP
    # =========================================================================

    async def on_message(self, message: discord.Message) -> None:
        """Handle message for XP gain."""
        # Basic validation
        if message.author.bot or not message.guild:
            return

        # Only track XP in main server
        if message.guild.id != config.GUILD_ID:
            return

        # Ignore slash commands and bot commands
        if message.content.startswith("/"):
            return

        # Ignore XP-excluded channels (e.g., prison)
        if message.channel.id in config.XP_IGNORED_CHANNELS:
            return

        member = message.author
        guild_id = message.guild.id
        user_id = member.id
        now = int(time.time())

        # Check in-memory cooldown cache first (avoids DB query)
        # Use lock to prevent race condition where concurrent messages bypass cooldown
        cache_key = (user_id, guild_id)

        async with self._cooldown_lock:
            last_xp = self._message_cooldowns.get(cache_key, 0)

            if now - last_xp < config.XP_MESSAGE_COOLDOWN:
                return  # Still on cooldown

            # Check for duplicate message (anti-spam) using hash for memory efficiency
            content_hash = hashlib.md5(
                message.content.lower().strip().encode(), usedforsecurity=False
            ).hexdigest()[:16]  # 16 chars is enough for duplicate detection
            last_hash = self._last_messages.get(cache_key)
            if last_hash and last_hash == content_hash:
                return  # Same message as before, no XP

            # Update last message tracker with hash (not full content)
            self._last_messages[cache_key] = content_hash

            # Update cache with current timestamp
            self._message_cooldowns[cache_key] = now

            # Periodically clean old entries inside the lock to prevent race conditions
            if len(self._message_cooldowns) > XP_COOLDOWN_CACHE_THRESHOLD:
                old_count = len(self._message_cooldowns)
                cutoff = now - config.XP_MESSAGE_COOLDOWN
                # Build new dicts first, then swap atomically with tuple assignment
                new_cooldowns = {
                    k: v for k, v in self._message_cooldowns.items()
                    if v > cutoff
                }
                new_messages = {
                    k: v for k, v in self._last_messages.items()
                    if k in new_cooldowns
                }
                # Atomic swap to keep both caches in sync
                self._message_cooldowns, self._last_messages = new_cooldowns, new_messages
                logger.tree("XP Cache Cleanup", [
                    ("Before", str(old_count)),
                    ("After", str(len(self._message_cooldowns))),
                    ("Removed", str(old_count - len(self._message_cooldowns))),
                ], emoji="🧹")

            # Hard limit enforcement - evict oldest entries if still too large
            if len(self._message_cooldowns) > XP_COOLDOWN_CACHE_MAX_SIZE:
                # Sort by timestamp and keep only the newest entries
                sorted_items = sorted(
                    self._message_cooldowns.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:XP_COOLDOWN_CACHE_MAX_SIZE]
                new_cooldowns = dict(sorted_items)
                new_messages = {
                    k: v for k, v in self._last_messages.items()
                    if k in new_cooldowns
                }
                # Atomic swap to keep both caches in sync
                self._message_cooldowns, self._last_messages = new_cooldowns, new_messages
                logger.tree("XP Cache Hard Limit Enforced", [
                    ("Max Size", str(XP_COOLDOWN_CACHE_MAX_SIZE)),
                ], emoji="⚠️")

        # Calculate XP with potential multipliers
        base_xp = random.randint(config.XP_MESSAGE_MIN, config.XP_MESSAGE_MAX)
        xp_amount = base_xp

        # Birthday bonus (3x) takes priority
        if has_birthday_bonus(member.id):
            xp_amount = int(base_xp * BIRTHDAY_XP_MULTIPLIER)
        elif isinstance(member, discord.Member) and member.premium_since is not None:
            xp_amount = int(base_xp * config.XP_BOOSTER_MULTIPLIER)

        # Add XP
        await self._grant_xp(member, xp_amount, "message")

        # Track additional metrics (non-blocking)
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            est = ZoneInfo("America/New_York")
            now_est = datetime.now(est)
            today_date = now_est.strftime("%Y-%m-%d")
            current_hour = now_est.hour

            # User-level tracking
            db.update_streak(user_id, guild_id, today_date)
            db.set_first_message_at(user_id, guild_id, now)
            db.increment_activity_hour(user_id, guild_id, current_hour)
            db.update_last_active(user_id, guild_id, now)

            # Server-level tracking
            db.increment_daily_messages(guild_id, today_date)
            db.increment_server_hour_activity(guild_id, current_hour, "message")
            db.increment_channel_messages(
                message.channel.id,
                guild_id,
                message.channel.name
            )

            # Track DAU (unique users) - use cache to avoid duplicate counts
            dau_key = (user_id, guild_id, today_date)
            async with self._dau_cache_lock:
                if dau_key not in self._dau_cache:
                    self._dau_cache.add(dau_key)
                    db.increment_daily_unique_user(guild_id, today_date)

                    # Clean cache when it gets large (removes stale dates)
                    if len(self._dau_cache) > 1000:
                        old_size = len(self._dau_cache)
                        self._dau_cache = {k for k in self._dau_cache if k[2] == today_date}
                        logger.tree("DAU Cache Cleanup", [
                            ("Before", str(old_size)),
                            ("After", str(len(self._dau_cache))),
                        ], emoji="🧹")
        except Exception as e:
            logger.tree("Metrics Track Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    # =========================================================================
    # Presence Tracking
    # =========================================================================

    async def on_presence_update(
        self,
        before: discord.Member,
        after: discord.Member
    ) -> None:
        """Track user activity based on presence changes (online/idle/dnd)."""
        if after.bot:
            return

        # Only track in main server
        if after.guild.id != config.GUILD_ID:
            return

        # Update last_active_at when user becomes active (not offline)
        # This includes: online, idle, dnd
        if after.status != discord.Status.offline and before.status == discord.Status.offline:
            now = int(time.time())
            db.update_last_active(after.id, after.guild.id, now)

    # =========================================================================
    # Voice XP
    # =========================================================================

    async def on_voice_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ) -> None:
        """Track voice channel joins/leaves for XP."""
        if member.bot:
            return

        # Only track XP in main server
        if member.guild.id != config.GUILD_ID:
            return

        guild_id = member.guild.id
        user_id = member.id

        # Ensure guild dict exists (with lock to prevent race condition)
        async with self._voice_sessions_lock:
            if guild_id not in self._voice_sessions:
                self._voice_sessions[guild_id] = {}

        # Determine actual channel changes
        left_voice = before.channel and (not after.channel or before.channel.id != after.channel.id)
        joined_voice = after.channel and (not before.channel or after.channel.id != before.channel.id)

        if joined_voice and after.channel:
            # User joined a voice channel - start tracking
            self._voice_sessions[guild_id][user_id] = time.time()

            # If user joined already muted, start mute tracking
            if after.self_mute or after.mute:
                self._mute_timestamps[user_id] = time.time()
                logger.tree("Voice Mute Tracking Started", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                    ("Channel", after.channel.name),
                    ("Type", "Server mute" if after.mute else "Self mute"),
                    ("Note", "Joined already muted"),
                ], emoji="🔇")

            # Track total voice sessions
            db.increment_voice_sessions(user_id, guild_id)

            logger.tree("Voice XP Session Started", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Channel", after.channel.name),
                ("Channel ID", str(after.channel.id)),
            ], emoji="🎤")

        elif left_voice:
            # Calculate session duration for longest session tracking
            join_time = self._voice_sessions[guild_id].get(user_id)
            session_minutes = 0
            if join_time:
                session_minutes = int((time.time() - join_time) / 60)
                if session_minutes > 0:
                    db.update_longest_voice_session(user_id, guild_id, session_minutes)

            # User left voice - remove from tracking (XP already awarded by loop)
            self._voice_sessions[guild_id].pop(user_id, None)
            # Clear mute tracking
            self._mute_timestamps.pop(user_id, None)

            # Calculate estimated XP earned (actual may vary based on channel conditions)
            base_xp = session_minutes * config.XP_VOICE_PER_MIN
            if member.premium_since is not None:
                estimated_xp = int(base_xp * config.XP_BOOSTER_MULTIPLIER)
                xp_display = f"~{estimated_xp} (2x boost)"
            else:
                estimated_xp = base_xp
                xp_display = f"~{estimated_xp}"

            logger.tree("Voice XP Session Ended", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Channel", before.channel.name if before.channel else "Unknown"),
                ("Duration", f"{session_minutes} min"),
                ("XP Earned", xp_display),
            ], emoji="🔇")

        # Track mute state changes for anti-AFK (only if still in voice)
        if after.channel:
            is_muted = after.self_mute or after.mute  # Self-mute or server mute
            was_muted = before.self_mute or before.mute

            if is_muted and not was_muted:
                # User just became muted - start tracking
                self._mute_timestamps[user_id] = time.time()
                logger.tree("Voice Mute Tracking Started", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                    ("Channel", after.channel.name),
                    ("Type", "Server mute" if after.mute else "Self mute"),
                ], emoji="🔇")
            elif not is_muted and was_muted:
                # User unmuted - clear tracking
                mute_duration = None
                if user_id in self._mute_timestamps:
                    mute_duration = int((time.time() - self._mute_timestamps[user_id]) / 60)
                self._mute_timestamps.pop(user_id, None)
                logger.tree("Voice Mute Tracking Cleared", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                    ("Channel", after.channel.name),
                    ("Muted For", f"{mute_duration} min" if mute_duration else "Unknown"),
                ], emoji="🔊")

    async def _run_with_restart(self, coro_func, name: str) -> None:
        """Wrapper that restarts a coroutine if it crashes unexpectedly."""
        while not self.bot.is_closed():
            try:
                await coro_func()
            except asyncio.CancelledError:
                logger.tree(f"{name} Cancelled", [], emoji="⏹️")
                break
            except Exception as e:
                logger.error_tree(f"{name} Crashed - Restarting", e)
                await asyncio.sleep(5)  # Brief pause before restart

    async def _voice_xp_loop(self) -> None:
        """Background task that awards voice XP every minute."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                await asyncio.sleep(60)  # Wait 1 minute

                for guild_id, sessions in list(self._voice_sessions.items()):
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        # Guild no longer accessible, clear sessions
                        self._voice_sessions.pop(guild_id, None)
                        continue

                    # Get users who have been in voice for at least 1 minute
                    now = time.time()
                    users_to_reward = []
                    stale_users = []

                    for user_id, join_time in list(sessions.items()):
                        member = guild.get_member(user_id)

                        # Check member exists first before any attribute access
                        if not member:
                            stale_users.append((user_id, "Unknown"))
                            continue

                        # Capture voice state once to avoid race conditions
                        voice = member.voice
                        channel = voice.channel if voice else None

                        if not channel:
                            stale_users.append((user_id, member.name))
                            continue

                        # Skip AFK channel
                        if guild.afk_channel and channel.id == guild.afk_channel.id:
                            continue

                        # Skip ignored channels (bot-managed VCs like Quran)
                        if channel.id in config.VC_IGNORED_CHANNELS:
                            continue

                        # Anti-abuse: Require at least 2 non-bot users in channel
                        human_count = sum(1 for m in channel.members if not m.bot)
                        if human_count < 2:
                            continue

                        # Anti-abuse: No XP if server deafened (not participating)
                        if voice.deaf:
                            continue

                        # Anti-abuse: No XP if muted for > 1 hour (AFK farming prevention)
                        is_muted = voice.self_mute or voice.mute
                        if is_muted:
                            mute_start = self._mute_timestamps.get(user_id)
                            if mute_start:
                                mute_duration = now - mute_start
                                if mute_duration > 3600:  # 1 hour
                                    logger.tree("Voice XP Blocked (AFK Mute)", [
                                        ("User", f"{member.name} ({member.display_name})"),
                                        ("ID", str(member.id)),
                                        ("Channel", channel.name),
                                        ("Muted For", f"{int(mute_duration / 60)} min"),
                                    ], emoji="🚫")
                                    continue

                        if now - join_time >= 60:
                            users_to_reward.append(member)

                    # Remove stale entries (users who left but event was missed)
                    if stale_users:
                        for user_id, user_name in stale_users:
                            sessions.pop(user_id, None)
                        logger.tree("Stale Voice Sessions Cleaned", [
                            ("Count", str(len(stale_users))),
                            ("Users", ", ".join(name for _, name in stale_users[:5]) + ("..." if len(stale_users) > 5 else "")),
                            ("Guild", guild.name),
                        ], emoji="🧹")

                    # Award XP
                    for member in users_to_reward:
                        xp_amount = config.XP_VOICE_PER_MIN

                        # Birthday bonus (3x) takes priority
                        if has_birthday_bonus(member.id):
                            xp_amount = int(xp_amount * BIRTHDAY_XP_MULTIPLIER)
                        elif member.premium_since is not None:
                            xp_amount = int(xp_amount * config.XP_BOOSTER_MULTIPLIER)

                        await self._grant_xp(member, xp_amount, "voice")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error_tree("Voice XP Loop Error", e)
                await asyncio.sleep(60)  # Wait before retrying

    async def _cache_cleanup_loop(self) -> None:
        """Background task that cleans stale cache entries every hour."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                await asyncio.sleep(3600)  # Wait 1 hour

                now = time.time()
                cleaned = {"mute": 0, "messages": 0, "cooldowns": 0, "dau": 0}

                # Clean stale mute timestamps (> 2 hours old)
                # These can accumulate if voice events are missed
                mute_cutoff = now - 7200  # 2 hours
                stale_mutes = [
                    uid for uid, ts in self._mute_timestamps.items()
                    if ts < mute_cutoff
                ]
                for uid in stale_mutes:
                    self._mute_timestamps.pop(uid, None)
                    cleaned["mute"] += 1

                # Clean old cooldown entries (> cooldown period)
                cooldown_cutoff = now - config.XP_MESSAGE_COOLDOWN
                old_cooldowns = {
                    k: v for k, v in self._message_cooldowns.items()
                    if v > cooldown_cutoff
                }
                cleaned["cooldowns"] = len(self._message_cooldowns) - len(old_cooldowns)
                self._message_cooldowns = old_cooldowns

                # Clean last messages to match cooldowns
                old_messages = {
                    k: v for k, v in self._last_messages.items()
                    if k in self._message_cooldowns
                }
                cleaned["messages"] = len(self._last_messages) - len(old_messages)
                self._last_messages = old_messages

                # Clean DAU cache - remove old dates (keep only today)
                from datetime import datetime
                from zoneinfo import ZoneInfo
                est = ZoneInfo("America/New_York")
                today_date = datetime.now(est).strftime("%Y-%m-%d")
                async with self._dau_cache_lock:
                    old_dau_size = len(self._dau_cache)
                    self._dau_cache = {k for k in self._dau_cache if k[2] == today_date}
                    cleaned["dau"] = old_dau_size - len(self._dau_cache)

                # Only log if we cleaned something
                if any(v > 0 for v in cleaned.values()):
                    logger.tree("XP Cache Cleanup (Hourly)", [
                        ("Mute Timestamps", str(cleaned["mute"])),
                        ("Cooldowns", str(cleaned["cooldowns"])),
                        ("Last Messages", str(cleaned["messages"])),
                        ("DAU Entries", str(cleaned["dau"])),
                        ("Remaining", f"{len(self._message_cooldowns)} cooldowns, {len(self._mute_timestamps)} mutes, {len(self._dau_cache)} dau"),
                    ], emoji="🧹")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error_tree("Cache Cleanup Loop Error", e)
                await asyncio.sleep(3600)

    # =========================================================================
    # Core XP Logic
    # =========================================================================

    async def _grant_xp(
        self,
        member: discord.Member,
        amount: int,
        source: str
    ) -> None:
        """
        Grant XP to a member, handling level ups and role rewards.

        Args:
            member: Discord member to grant XP to
            amount: Amount of XP to grant
            source: "message" or "voice"
        """
        try:
            now = int(time.time())

            # Add XP to database
            result = db.add_xp(member.id, member.guild.id, amount, source)

            # Track first message and last active
            if source == "message":
                db.set_first_message_at(member.id, member.guild.id, now)
            db.update_last_active(member.id, member.guild.id, now)

            # Update streak
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            db.update_streak(member.id, member.guild.id, today)

            old_level = result["old_level"]
            new_level = level_from_xp(result["new_xp"])

            # Check for level up
            if new_level > old_level:
                # Update level in database
                db.set_user_level(member.id, member.guild.id, new_level)

                logger.tree("Level Up!", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                    ("Level", f"{old_level} -> {new_level}"),
                    ("XP", format_xp(result["new_xp"])),
                ], emoji="🎉")

                # Award role rewards and send DM if any earned
                roles_earned = await self._check_role_rewards(member, old_level, new_level)

                # Only DM when they unlock a role reward (not every level)
                if roles_earned:
                    await self._send_reward_dm(member, new_level, roles_earned)

                # Grant casino currency for level up (to bank)
                if self.bot.currency_service and self.bot.currency_service.is_enabled():
                    success, msg = await self.bot.currency_service.grant(
                        user_id=member.id,
                        amount=10000,
                        reason=f"Level up to {new_level}",
                        target="bank"
                    )
                    if success:
                        logger.tree("Level Up Currency Reward", [
                            ("User", f"{member.name} ({member.display_name})"),
                            ("ID", str(member.id)),
                            ("Level", str(new_level)),
                            ("Amount", "10,000 coins → Bank"),
                        ], emoji="🏦")

        except Exception as e:
            logger.error_tree("XP Grant Error", e, [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Amount", str(amount)),
                ("Source", source),
            ])

    async def _check_role_rewards(
        self,
        member: discord.Member,
        old_level: int,
        new_level: int
    ) -> list:
        """Check and award role rewards for level ups.

        Returns:
            List of (level, role) tuples that were awarded
        """
        if not config.XP_ROLE_REWARDS:
            return []

        # Skip giving roles to owner (they still get XP, just no roles)
        if member.id == config.OWNER_ID:
            logger.tree("Role Reward Skipped (Owner)", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Level", str(new_level)),
                ("Reason", "Owner excluded from level roles"),
            ], emoji="👑")
            return []

        roles_to_add = []
        roles_to_remove = []
        earned = []  # (level, role) tuples

        # Get all XP role IDs for removal check
        all_xp_role_ids = set(config.XP_ROLE_REWARDS.values())

        for level, role_id in sorted(config.XP_ROLE_REWARDS.items()):
            # Award roles for levels between old and new (inclusive of new)
            if old_level < level <= new_level:
                role = member.guild.get_role(role_id)
                if not role:
                    logger.tree("Role Reward Not Found", [
                        ("User", f"{member.name} ({member.display_name})"),
                        ("ID", str(member.id)),
                        ("Level", str(level)),
                        ("Role ID", str(role_id)),
                        ("Reason", "Role ID not found in guild"),
                    ], emoji="⚠️")
                    continue
                if role not in member.roles:
                    roles_to_add.append(role)
                    earned.append((level, role))

        # Find the highest role level the user should have for their new level
        highest_applicable_level = None
        for level in sorted(config.XP_ROLE_REWARDS.keys()):
            if level <= new_level:
                highest_applicable_level = level
            else:
                break

        # Only remove old XP roles if they're BELOW the highest applicable role
        # (e.g., level 6 user keeps level 5 role until they reach level 10)
        if highest_applicable_level is not None:
            for member_role in member.roles:
                if member_role.id in all_xp_role_ids:
                    # Find what level this role is for
                    for level, role_id in config.XP_ROLE_REWARDS.items():
                        if role_id == member_role.id and level < highest_applicable_level:
                            # This is an old level role below their current tier
                            if member_role not in roles_to_add:
                                roles_to_remove.append(member_role)
                            break

        if roles_to_add or roles_to_remove:
            try:
                # Remove old roles first
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason=f"XP Level {new_level} - removing old roles")
                    for role in roles_to_remove:
                        logger.tree("Old Role Removed", [
                            ("User", f"{member.name} ({member.display_name})"),
                            ("ID", str(member.id)),
                            ("Role", role.name),
                            ("Role ID", str(role.id)),
                            ("Reason", f"Upgraded to Level {new_level}"),
                        ], emoji="🔄")

                # Add new roles
                if roles_to_add:
                    await member.add_roles(*roles_to_add, reason=f"XP Level {new_level} reward")

                    for level, role in earned:
                        perk = LEVEL_PERKS.get(level, "")
                        logger.tree("Role Reward Granted", [
                            ("User", f"{member.name} ({member.display_name})"),
                            ("ID", str(member.id)),
                            ("Level", str(level)),
                            ("Role", role.name),
                            ("Role ID", str(role.id)),
                            ("Perk", perk if perk else "None"),
                        ], emoji="🏆")

                return earned

            except discord.HTTPException as e:
                logger.error_tree("Role Reward Failed", e, [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                    ("Roles to Add", ", ".join(r.name for r in roles_to_add)),
                    ("Roles to Remove", ", ".join(r.name for r in roles_to_remove)),
                ])
                return []

        return []

    async def _send_reward_dm(
        self,
        member: discord.Member,
        new_level: int,
        roles_earned: list
    ) -> None:
        """Send DM notification when user earns role rewards.

        Only called when roles are actually earned, not on every level up.

        Args:
            member: The member who earned rewards
            new_level: Their new level
            roles_earned: List of (level, role) tuples that were awarded
        """
        try:
            # Build unlocked section
            unlocked_lines = []
            for level, role in roles_earned:
                perk = LEVEL_PERKS.get(level)
                if perk:
                    unlocked_lines.append(f"**{role.name}** (Level {level})\n└ {perk}")
                else:
                    unlocked_lines.append(f"**{role.name}** (Level {level})")

            unlocked_text = "\n\n".join(unlocked_lines)

            # Find next reward level
            next_reward_level = None
            next_reward_role = None
            next_perk = None

            for level in sorted(config.XP_ROLE_REWARDS.keys()):
                if level > new_level:
                    next_reward_level = level
                    role_id = config.XP_ROLE_REWARDS[level]
                    next_reward_role = member.guild.get_role(role_id)
                    next_perk = LEVEL_PERKS.get(level)
                    if not next_reward_role:
                        logger.tree("Next Reward Role Not Found", [
                            ("User", f"{member.name} ({member.display_name})"),
                            ("Level", str(level)),
                            ("Role ID", str(role_id)),
                            ("Reason", "Role ID not found in guild"),
                        ], emoji="⚠️")
                    break

            # Build embed
            embed = discord.Embed(
                title="🏆 Rewards Unlocked!",
                description=f"You've reached **Level {new_level}** in **{member.guild.name}**!",
                color=COLOR_GOLD,
            )

            embed.add_field(
                name="Unlocked",
                value=unlocked_text,
                inline=False,
            )

            # Show next reward if exists
            if next_reward_level and next_reward_role:
                next_text = f"**{next_reward_role.name}** at Level {next_reward_level}"
                if next_perk:
                    next_text += f"\n└ {next_perk}"
                embed.add_field(
                    name="Next Reward",
                    value=next_text,
                    inline=False,
                )
            elif new_level >= 100:
                embed.add_field(
                    name="🎊 Max Level!",
                    value="You've unlocked everything!",
                    inline=False,
                )

            embed.set_thumbnail(url=member.display_avatar.url)
            set_footer(embed)

            await member.send(embed=embed)

            logger.tree("Reward DM Sent", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Level", str(new_level)),
                ("Roles Earned", ", ".join(r.name for _, r in roles_earned)),
                ("Next Reward", f"Level {next_reward_level}" if next_reward_level else "None"),
            ], emoji="📬")

        except discord.Forbidden:
            # User has DMs disabled - log as info (not warning/error)
            logger.tree("Reward DM Skipped", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Level", str(new_level)),
                ("Reason", "DMs disabled"),
            ], emoji="📭")

        except Exception as e:
            logger.error_tree("Reward DM Error", e, [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Level", str(new_level)),
            ])

    # =========================================================================
    # Role Sync (Startup + Midnight)
    # =========================================================================

    @tasks.loop(time=dt_time(hour=5, minute=0))  # 5:00 UTC = Midnight EST
    async def midnight_role_sync(self) -> None:
        """Run maintenance tasks at midnight EST."""
        logger.tree("Midnight Maintenance Started", [], emoji="🕛")

        # 1. Clear DAU cache (new day = new tracking)
        async with self._dau_cache_lock:
            old_dau_size = len(self._dau_cache)
            self._dau_cache.clear()

        # 2. Clear stale mute timestamps
        stale_mutes = len(self._mute_timestamps)
        self._mute_timestamps.clear()

        # 3. Clear message cooldowns
        stale_cooldowns = len(self._message_cooldowns)
        self._message_cooldowns.clear()

        if old_dau_size > 0 or stale_mutes > 0 or stale_cooldowns > 0:
            logger.tree("Midnight Cache Cleanup", [
                ("DAU Entries", str(old_dau_size)),
                ("Mute Timestamps", str(stale_mutes)),
                ("Message Cooldowns", str(stale_cooldowns)),
            ], emoji="🧹")

        # 4. Sync active/inactive user status
        await self._sync_active_status()

        # 5. Sync XP roles
        await self._sync_roles()

        # 6. Rate limiter cleanup (backup - also triggers on week boundary)
        try:
            from src.services.rate_limiter import get_rate_limiter
            rate_limiter = get_rate_limiter()
            deleted = rate_limiter.cleanup_old_records(weeks_to_keep=4)
            if deleted > 0:
                logger.tree("Rate Limit Records Cleaned", [
                    ("Deleted", str(deleted)),
                ], emoji="🧹")
        except Exception as e:
            logger.tree("Rate Limit Cleanup Failed", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # 7. Guild protection check - leave unauthorized guilds
        try:
            await self.bot._leave_unauthorized_guilds()
        except Exception as e:
            logger.tree("Guild Protection Check Failed", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        logger.tree("Midnight Maintenance Complete", [], emoji="✅")

    @midnight_role_sync.before_loop
    async def before_midnight_sync(self) -> None:
        """Wait for bot to be ready before starting midnight sync task."""
        await self.bot.wait_until_ready()

    async def _sync_active_status(self) -> None:
        """Sync is_active status by comparing DB users with actual guild members."""
        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            logger.tree("Active Status Sync Skipped", [
                ("Reason", "Main guild not found"),
            ], emoji="⚠️")
            return

        # Get all user IDs from database
        all_db_users = db.get_all_users_with_levels(config.GUILD_ID)
        if not all_db_users:
            logger.tree("Active Status Sync Skipped", [
                ("Reason", "No users in database"),
            ], emoji="ℹ️")
            return

        db_user_ids = {user_id for user_id, _ in all_db_users}

        # Get all current member IDs
        current_member_ids = {m.id for m in guild.members if not m.bot}

        # Find who left and who's still here
        left_users = db_user_ids - current_member_ids
        active_users = db_user_ids & current_member_ids

        # Batch update inactive users
        for user_id in left_users:
            db.set_user_inactive(user_id, config.GUILD_ID)

        # Batch update active users
        for user_id in active_users:
            db.set_user_active(user_id, config.GUILD_ID)

        logger.tree("Active Status Sync Complete", [
            ("Total DB Users", str(len(db_user_ids))),
            ("Active", str(len(active_users))),
            ("Inactive", str(len(left_users))),
        ], emoji="✅")

    async def _sync_roles(self) -> None:
        """Sync XP roles - shared by startup and midnight sync."""
        if not config.XP_ROLE_REWARDS:
            logger.tree("Role Sync Skipped", [
                ("Reason", "No role rewards configured"),
            ], emoji="ℹ️")
            return

        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            logger.tree("Role Sync Skipped", [
                ("Reason", "Main guild not found"),
            ], emoji="⚠️")
            return

        logger.tree("Role Sync Started", [
            ("Guild", guild.name),
        ], emoji="🔄")

        # Get all users with level >= 1 from database
        users_data = db.get_all_users_with_levels(config.GUILD_ID)
        if not users_data:
            logger.tree("Role Sync Complete", [
                ("Users Checked", "0"),
                ("Roles Fixed", "0"),
            ], emoji="✅")
            return

        # Get all XP role IDs
        all_xp_role_ids = set(config.XP_ROLE_REWARDS.values())

        # Find the correct role for each level
        def get_role_for_level(level: int) -> Optional[int]:
            """Get the highest role ID the user should have for their level."""
            applicable_role = None
            for role_level, role_id in sorted(config.XP_ROLE_REWARDS.items()):
                if role_level <= level:
                    applicable_role = role_id
                else:
                    break
            return applicable_role

        fixed_count = 0
        checked_count = 0

        for user_id, level in users_data:
            if level < 1:
                continue

            # Skip owner
            if user_id == config.OWNER_ID:
                continue

            member = guild.get_member(user_id)
            if not member:
                continue

            checked_count += 1

            # Get the role they should have
            correct_role_id = get_role_for_level(level)
            if not correct_role_id:
                continue

            correct_role = guild.get_role(correct_role_id)
            if not correct_role:
                logger.tree("Role Sync Skipped - Role Missing", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("Level", str(level)),
                    ("Missing Role ID", str(correct_role_id)),
                    ("Action", "Check SYRIA_XP_ROLES config"),
                ], emoji="⚠️")
                continue

            # Check current roles
            has_correct_role = correct_role in member.roles
            roles_to_add = []
            roles_to_remove = []

            if not has_correct_role:
                roles_to_add.append(correct_role)

            # Check for old XP roles that should be removed
            for member_role in member.roles:
                if member_role.id in all_xp_role_ids and member_role.id != correct_role_id:
                    roles_to_remove.append(member_role)

            # Apply changes
            if roles_to_add or roles_to_remove:
                try:
                    if roles_to_remove:
                        await member.remove_roles(*roles_to_remove, reason="XP Role Sync - removing old roles")
                    if roles_to_add:
                        await member.add_roles(*roles_to_add, reason="XP Role Sync - adding missing role")

                    fixed_count += 1
                    logger.tree("Role Sync Fixed", [
                        ("User", f"{member.name} ({member.display_name})"),
                        ("ID", str(member.id)),
                        ("Level", str(level)),
                        ("Added", correct_role.name if roles_to_add else "None"),
                        ("Removed", ", ".join(r.name for r in roles_to_remove) if roles_to_remove else "None"),
                    ], emoji="🔧")

                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.5)

                except discord.HTTPException as e:
                    logger.tree("Role Sync Failed", [
                        ("User", f"{member.name}"),
                        ("ID", str(member.id)),
                        ("Error", str(e)[:50]),
                    ], emoji="⚠️")

        logger.tree("Role Sync Complete", [
            ("Users Checked", str(checked_count)),
            ("Roles Fixed", str(fixed_count)),
        ], emoji="✅")

    async def restore_member_roles(self, member: discord.Member) -> None:
        """Restore XP roles for a member who rejoined the server."""
        if not config.XP_ROLE_REWARDS:
            return

        if member.bot:
            return

        # Get user's XP data
        xp_data = db.get_user_xp(member.id, member.guild.id)
        if not xp_data or xp_data["level"] < 1:
            return

        level = xp_data["level"]

        # Find the correct role for their level
        correct_role_id = None
        for role_level, role_id in sorted(config.XP_ROLE_REWARDS.items()):
            if role_level <= level:
                correct_role_id = role_id
            else:
                break

        if not correct_role_id:
            return

        correct_role = member.guild.get_role(correct_role_id)
        if not correct_role:
            logger.tree("Role Restore Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Level", str(level)),
                ("Reason", f"Role {correct_role_id} not found"),
            ], emoji="⚠️")
            return

        # Check if they already have the role (shouldn't happen on rejoin, but check anyway)
        if correct_role in member.roles:
            return

        try:
            await member.add_roles(correct_role, reason=f"XP Role Restore - Level {level}")
            logger.tree("XP Role Restored", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Level", str(level)),
                ("XP", str(xp_data["xp"])),
                ("Role", correct_role.name),
            ], emoji="🔄")
        except discord.HTTPException as e:
            logger.tree("Role Restore Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
                ("Level", str(level)),
                ("Error", str(e)[:50]),
            ], emoji="❌")
