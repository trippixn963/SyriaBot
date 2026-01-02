"""
XP System - Service
===================

Main XP service handling message and voice XP gains.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import TYPE_CHECKING, Dict, Optional

import discord

from src.core.config import config
from src.core.colors import COLOR_GOLD
from src.core.constants import XP_COOLDOWN_CACHE_THRESHOLD
from src.core.logger import log
from src.services.database import db
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

    def __init__(self, bot: "SyriaBot"):
        self.bot = bot

        # Track users in voice channels: {guild_id: {user_id: join_timestamp}}
        self._voice_sessions: Dict[int, Dict[int, float]] = {}

        # In-memory message cooldown cache: {(user_id, guild_id): timestamp}
        # Avoids DB query on every message - most will fail cooldown check
        self._message_cooldowns: Dict[tuple, int] = {}

        # Track last message content per user to prevent duplicate spam
        self._last_messages: Dict[tuple, str] = {}  # {(user_id, guild_id): content}

        # Background task for voice XP
        self._voice_xp_task: Optional[asyncio.Task] = None

    async def setup(self) -> None:
        """Initialize XP service."""
        # Start voice XP background task
        self._voice_xp_task = asyncio.create_task(self._voice_xp_loop())

        # Initialize voice sessions for users already in voice (main server only)
        main_guild = self.bot.get_guild(config.GUILD_ID)
        if main_guild:
            self._voice_sessions[main_guild.id] = {}
            for vc in main_guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        self._voice_sessions[main_guild.id][member.id] = time.time()

        log.tree("XP Service Started", [
            ("Message XP", f"{config.XP_MESSAGE_MIN}-{config.XP_MESSAGE_MAX}"),
            ("Voice XP", f"{config.XP_VOICE_PER_MIN}/min"),
            ("Cooldown", f"{config.XP_MESSAGE_COOLDOWN}s"),
            ("Booster Multiplier", f"{config.XP_BOOSTER_MULTIPLIER}x"),
            ("Role Rewards", str(len(config.XP_ROLE_REWARDS))),
        ], emoji="⬆️")

    async def stop(self) -> None:
        """Cleanup XP service."""
        if self._voice_xp_task:
            self._voice_xp_task.cancel()
            try:
                await self._voice_xp_task
            except asyncio.CancelledError:
                pass

        log.tree("XP Service Stopped", [
            ("Active Voice Sessions", str(sum(len(s) for s in self._voice_sessions.values()))),
            ("Cached Cooldowns", str(len(self._message_cooldowns))),
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
        cache_key = (user_id, guild_id)
        last_xp = self._message_cooldowns.get(cache_key, 0)

        if now - last_xp < config.XP_MESSAGE_COOLDOWN:
            return  # Still on cooldown

        # Check for duplicate message (anti-spam)
        content_lower = message.content.lower().strip()
        last_content = self._last_messages.get(cache_key)
        if last_content and last_content == content_lower:
            return  # Same message as before, no XP

        # Update last message tracker
        self._last_messages[cache_key] = content_lower

        # Update cache with current timestamp
        self._message_cooldowns[cache_key] = now

        # Periodically clean old entries (every ~100 users)
        if len(self._message_cooldowns) > XP_COOLDOWN_CACHE_THRESHOLD:
            old_count = len(self._message_cooldowns)
            cutoff = now - config.XP_MESSAGE_COOLDOWN
            self._message_cooldowns = {
                k: v for k, v in self._message_cooldowns.items()
                if v > cutoff
            }
            # Also clean _last_messages to match (keep only users still on cooldown)
            self._last_messages = {
                k: v for k, v in self._last_messages.items()
                if k in self._message_cooldowns
            }
            log.tree("XP Cache Cleanup", [
                ("Before", str(old_count)),
                ("After", str(len(self._message_cooldowns))),
                ("Removed", str(old_count - len(self._message_cooldowns))),
            ], emoji="🧹")

        # Calculate XP with potential booster multiplier
        base_xp = random.randint(config.XP_MESSAGE_MIN, config.XP_MESSAGE_MAX)

        if member.premium_since is not None:
            xp_amount = int(base_xp * config.XP_BOOSTER_MULTIPLIER)
        else:
            xp_amount = base_xp

        # Add XP
        await self._grant_xp(member, xp_amount, "message")

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

        # Ensure guild dict exists
        if guild_id not in self._voice_sessions:
            self._voice_sessions[guild_id] = {}

        # Determine actual channel changes
        left_voice = before.channel and (not after.channel or before.channel.id != after.channel.id)
        joined_voice = after.channel and (not before.channel or after.channel.id != before.channel.id)

        if joined_voice and after.channel:
            # User joined a voice channel - start tracking
            self._voice_sessions[guild_id][user_id] = time.time()

            # Track total voice sessions
            db.increment_voice_sessions(user_id, guild_id)

            log.tree("Voice XP Session Started", [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
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

            log.tree("Voice XP Session Ended", [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
                ("Channel", before.channel.name if before.channel else "Unknown"),
                ("Duration", f"{session_minutes} min"),
            ], emoji="🔇")

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
                        # Validate user is still in voice (cleanup stale entries)
                        if not member or not member.voice or not member.voice.channel:
                            stale_users.append(user_id)
                            continue

                        channel = member.voice.channel

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
                        if member.voice.deaf:
                            continue

                        if now - join_time >= 60:
                            users_to_reward.append(member)

                    # Remove stale entries (users who left but event was missed)
                    for user_id in stale_users:
                        sessions.pop(user_id, None)

                    # Award XP
                    for member in users_to_reward:
                        xp_amount = config.XP_VOICE_PER_MIN

                        if member.premium_since is not None:
                            xp_amount = int(xp_amount * config.XP_BOOSTER_MULTIPLIER)

                        await self._grant_xp(member, xp_amount, "voice")

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error_tree("Voice XP Loop Error", e)
                await asyncio.sleep(60)  # Wait before retrying

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

                log.tree("Level Up!", [
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

        except Exception as e:
            log.error_tree("XP Grant Error", e, [
                ("User", str(member)),
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
            log.tree("Role Reward Skipped (Owner)", [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
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
                    log.tree("Role Reward Not Found", [
                        ("User", f"{member.name} ({member.display_name})"),
                        ("User ID", str(member.id)),
                        ("Level", str(level)),
                        ("Role ID", str(role_id)),
                        ("Reason", "Role ID not found in guild"),
                    ], emoji="⚠️")
                    continue
                if role not in member.roles:
                    roles_to_add.append(role)
                    earned.append((level, role))

        # Find old XP roles to remove (any XP role below new level)
        for member_role in member.roles:
            if member_role.id in all_xp_role_ids:
                # Find what level this role is for
                for level, role_id in config.XP_ROLE_REWARDS.items():
                    if role_id == member_role.id and level < new_level:
                        # This is an old level role, mark for removal
                        if member_role not in roles_to_add:
                            roles_to_remove.append(member_role)
                        break

        if roles_to_add or roles_to_remove:
            try:
                # Remove old roles first
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason=f"XP Level {new_level} - removing old roles")
                    for role in roles_to_remove:
                        log.tree("Old Role Removed", [
                            ("User", f"{member.name} ({member.display_name})"),
                            ("User ID", str(member.id)),
                            ("Role", role.name),
                            ("Role ID", str(role.id)),
                            ("Reason", f"Upgraded to Level {new_level}"),
                        ], emoji="🔄")

                # Add new roles
                if roles_to_add:
                    await member.add_roles(*roles_to_add, reason=f"XP Level {new_level} reward")

                    for level, role in earned:
                        perk = LEVEL_PERKS.get(level, "")
                        log.tree("Role Reward Granted", [
                            ("User", f"{member.name} ({member.display_name})"),
                            ("User ID", str(member.id)),
                            ("Level", str(level)),
                            ("Role", role.name),
                            ("Role ID", str(role.id)),
                            ("Perk", perk if perk else "None"),
                        ], emoji="🏆")

                return earned

            except discord.HTTPException as e:
                log.error_tree("Role Reward Failed", e, [
                    ("User", str(member)),
                    ("User ID", str(member.id)),
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
                        log.tree("Next Reward Role Not Found", [
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

            log.tree("Reward DM Sent", [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
                ("Level", str(new_level)),
                ("Roles Earned", ", ".join(r.name for _, r in roles_earned)),
                ("Next Reward", f"Level {next_reward_level}" if next_reward_level else "None"),
            ], emoji="📬")

        except discord.Forbidden:
            # User has DMs disabled - log as info (not warning/error)
            log.tree("Reward DM Skipped", [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
                ("Level", str(new_level)),
                ("Reason", "DMs disabled"),
            ], emoji="📭")

        except Exception as e:
            log.error_tree("Reward DM Error", e, [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
                ("Level", str(new_level)),
            ])
