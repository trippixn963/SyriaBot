"""
SyriaBot - Action Commands Handler
==================================

Handles action commands: slap, hug, kiss, cry, etc.
Supports self-targets, multiple targets, and stats tracking.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import time
from collections import OrderedDict

import discord

from src.core.logger import log
from src.core.colors import COLOR_ERROR, COLOR_GOLD
from src.core.constants import DELETE_DELAY_SHORT
from src.services.action_service import action_service
from src.services.database import db
from src.utils.footer import set_footer


# Max cooldown cache size before cleanup
MAX_COOLDOWN_CACHE_SIZE = 100


class ActionHandler:
    """Handles action commands with GIFs."""

    # Action command cooldown (60 seconds)
    ACTION_COOLDOWN = 60

    def __init__(self) -> None:
        """Initialize the action handler."""
        self._cooldowns: OrderedDict[int, float] = OrderedDict()
        self._cooldown_lock = asyncio.Lock()

    async def _cleanup_cooldowns(self) -> None:
        """Remove expired cooldowns to prevent unbounded growth (thread-safe)."""
        if len(self._cooldowns) <= MAX_COOLDOWN_CACHE_SIZE:
            return

        async with self._cooldown_lock:
            now = time.time()
            # Build list of expired users safely
            expired_users = [
                uid for uid, ts in list(self._cooldowns.items())
                if now - ts > self.ACTION_COOLDOWN
            ]
            for uid in expired_users:
                self._cooldowns.pop(uid, None)  # Use pop to avoid KeyError

            # Evict oldest if still over limit
            while len(self._cooldowns) > MAX_COOLDOWN_CACHE_SIZE:
                try:
                    self._cooldowns.popitem(last=False)
                except KeyError:
                    break  # Dict is empty

    async def handle(self, message: discord.Message) -> bool:
        """
        Handle action commands like 'slap @user', 'hug @user', 'cry', etc.
        Supports:
        - Self-target for target actions (hug alone = self hug)
        - Multiple targets (slap @user1 @user2 = sends for each)
        - Stats tracking

        Returns True if an action was processed, False otherwise.
        """
        content = message.content.strip().lower()

        # Fast path: Check if first word could be an action
        first_word = content.split()[0] if content else ""
        if not action_service.is_action(first_word):
            return False

        # Strict matching: only allow action + mentions, no extra text
        # This prevents "kick boxing" from triggering "kick"
        words = content.split()
        for word in words[1:]:  # Skip the action word itself
            # Allow mentions (<@123> or <@!123>) but reject other text
            if not word.startswith("<@"):
                return False

        action = first_word
        user_id = message.author.id
        guild_id = message.guild.id

        # Check cooldown (atomically with lock to prevent race conditions)
        async with self._cooldown_lock:
            last_use = self._cooldowns.get(user_id, 0)
            time_since = time.time() - last_use
            if time_since < self.ACTION_COOLDOWN:
                remaining = self.ACTION_COOLDOWN - time_since
                cooldown_ends = int(time.time() + remaining)
                # Release lock before async operations
                on_cooldown = True
            else:
                # Record cooldown immediately while we have the lock
                self._cooldowns[user_id] = time.time()
                on_cooldown = False

        if on_cooldown:
            cooldown_msg = await message.reply(
                f"You're on cooldown. Try again <t:{cooldown_ends}:R>",
                mention_author=False
            )
            await asyncio.gather(
                message.delete(delay=DELETE_DELAY_SHORT),
                cooldown_msg.delete(delay=DELETE_DELAY_SHORT),
                return_exceptions=True
            )
            log.tree("Action Cooldown", [
                ("User", f"{message.author.name}"),
                ("ID", str(user_id)),
                ("Action", action),
                ("Ends", f"<t:{cooldown_ends}:R>"),
            ], emoji="⏳")
            return True

        # Cleanup old cooldowns (after releasing the main lock)
        await self._cleanup_cooldowns()

        # Build targets list
        targets = []
        is_self_action = action_service.is_self_action(action)
        is_target_action = action_service.is_target_action(action)

        if is_target_action:
            if message.mentions:
                # Filter out self-mentions and duplicates
                seen = set()
                for mention in message.mentions:
                    if mention.id != message.author.id and mention.id not in seen:
                        targets.append(mention)
                        seen.add(mention.id)

            # If no valid targets, treat as self-action (hug alone = self hug)
            if not targets:
                targets = [None]  # None means self-target
                log.tree("Action Self-Target", [
                    ("User", f"{message.author.name}"),
                    ("ID", str(user_id)),
                    ("Action", action),
                    ("Reason", "No targets, using self"),
                ], emoji="🎬")
        elif is_self_action:
            targets = [None]  # Self-actions have no target
        else:
            log.tree("Action Skipped", [
                ("User", f"{message.author.name}"),
                ("ID", str(user_id)),
                ("Action", action),
                ("Reason", "Invalid action type"),
            ], emoji="⚠️")
            return False

        # Process each target (combo support)
        user_mention = message.author.mention
        sent_count = 0

        for target in targets:
            # Log the action
            if target:
                log.tree("Action Command", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(user_id)),
                    ("Action", action),
                    ("Target", f"{target.name} ({target.display_name})"),
                    ("Target ID", str(target.id)),
                    ("Combo", f"{sent_count + 1}/{len(targets)}"),
                ], emoji="🎬")
            else:
                log.tree("Self Action Command", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(user_id)),
                    ("Action", action),
                ], emoji="🎬")

            # Fetch GIF (new GIF for each target in combo)
            gif_url = await action_service.get_action_gif(action)
            if not gif_url:
                log.tree("Action GIF Failed", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                    ("Action", action),
                    ("Reason", "API returned no URL"),
                ], emoji="⚠️")
                if sent_count == 0:
                    # Only show error if we haven't sent anything
                    embed = discord.Embed(
                        description="Failed to fetch GIF. Please try again.",
                        color=COLOR_ERROR
                    )
                    msg = await message.channel.send(embed=embed)
                    await msg.delete(delay=DELETE_DELAY_SHORT)
                continue

            # Build action text
            target_mention = target.mention if target else None
            action_text = action_service.get_action_message(action, user_mention, target_mention)

            # Create embed with GIF
            embed = discord.Embed(description=action_text, color=COLOR_GOLD)
            embed.set_image(url=gif_url)
            set_footer(embed)

            # Send embed
            await message.channel.send(embed=embed)
            sent_count += 1

            # Record stats (non-blocking)
            try:
                target_id = target.id if target else None
                await asyncio.to_thread(db.record_action, user_id, guild_id, action, target_id)
            except Exception as e:
                log.error_tree("Action Stats Record Failed", e, [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(user_id)),
                    ("Guild ID", str(guild_id)),
                    ("Action", action),
                    ("Target ID", str(target_id) if target_id else "None"),
                ])

            log.tree("Action Sent", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(user_id)),
                ("Action", action),
                ("Target", f"{target.name}" if target else "Self"),
                ("Channel", message.channel.name if hasattr(message.channel, 'name') else "DM"),
            ], emoji="✅")

            # Small delay between combo actions to avoid rate limits
            if len(targets) > 1 and sent_count < len(targets):
                await asyncio.sleep(0.5)

        return sent_count > 0


# Singleton instance
action_handler = ActionHandler()
