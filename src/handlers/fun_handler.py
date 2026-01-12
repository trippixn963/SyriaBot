"""
SyriaBot - Fun Commands Handler
===============================

Handles fun commands: ship, simp, howgay, howsmart, bodyfat.
Visual card generation with typo detection and sticky messages.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import difflib
import io
import time
from collections import OrderedDict
from typing import Optional

import discord

from src.core.logger import log
from src.core.config import config
from src.core.colors import COLOR_ERROR, COLOR_WARNING, COLOR_SYRIA_GREEN
from src.core.constants import DELETE_DELAY_SHORT
from src.services.fun import fun_service, generate_ship_card, generate_meter_card
from src.utils.footer import set_footer


# Max cooldown cache size before cleanup
MAX_COOLDOWN_CACHE_SIZE = 100


class FunHandler:
    """Handles fun commands with visual cards."""

    # Fun command cooldown (30 seconds - image generation is heavier)
    FUN_COOLDOWN = 30

    # Sticky message interval (every N messages)
    FUN_STICKY_INTERVAL = 30

    # Valid fun commands for typo detection
    FUN_COMMANDS = ("ship", "simp", "howgay", "howsmart", "bodyfat")

    def __init__(self) -> None:
        """Initialize the fun handler."""
        self._cooldowns: OrderedDict[int, float] = OrderedDict()
        self._channel_msg_count: int = 0
        self._sticky_message_id: Optional[int] = None

    def _cleanup_cooldowns(self) -> None:
        """Remove expired cooldowns to prevent unbounded growth."""
        if len(self._cooldowns) <= MAX_COOLDOWN_CACHE_SIZE:
            return

        now = time.time()
        expired_users = [
            uid for uid, ts in self._cooldowns.items()
            if now - ts > self.FUN_COOLDOWN
        ]
        for uid in expired_users:
            del self._cooldowns[uid]

        while len(self._cooldowns) > MAX_COOLDOWN_CACHE_SIZE:
            self._cooldowns.popitem(last=False)

    async def _send_sticky(self, channel: discord.TextChannel) -> None:
        """Send sticky message for fun commands channel."""
        # Delete previous sticky if exists
        if self._sticky_message_id:
            try:
                old_msg = await channel.fetch_message(self._sticky_message_id)
                await old_msg.delete()
            except discord.HTTPException:
                pass  # Message gone, forbidden, or API error - all ok

        embed = discord.Embed(
            title="🎮 Commands Channel",
            description=(
                "**⚠️ This channel does not earn XP.**\n\n"
                "`ship @user @user` — Compatibility %\n"
                "`howgay` `simp` `howsmart` `bodyfat` — Meters\n"
                "`hug` `kiss` `slap` `kick` etc — Actions"
            ),
            color=COLOR_SYRIA_GREEN
        )
        set_footer(embed)

        sticky_msg = await channel.send(embed=embed)
        self._sticky_message_id = sticky_msg.id
        self._channel_msg_count = 0

        log.tree("Fun Sticky Sent", [
            ("Channel", channel.name),
            ("Message ID", str(sticky_msg.id)),
        ], emoji="📌")

    async def handle(self, message: discord.Message) -> bool:
        """
        Handle fun commands: ship, simp, howgay, howsmart, bodyfat.
        Returns True if a command was processed, False otherwise.
        """
        content = message.content.strip().lower()
        parts = content.split()
        if not parts:
            return False

        command = parts[0]

        # Check for exact match
        if command not in self.FUN_COMMANDS:
            # Check for typos - only in the fun channel
            if config.FUN_COMMANDS_CHANNEL_ID and message.channel.id == config.FUN_COMMANDS_CHANNEL_ID:
                # Use difflib to find close matches (cutoff 0.6 = 60% similarity)
                matches = difflib.get_close_matches(command, self.FUN_COMMANDS, n=1, cutoff=0.6)
                if matches:
                    # Auto-correct to the matched command
                    command = matches[0]
                    log.tree("Fun Command Typo Corrected", [
                        ("User", f"{message.author.name}"),
                        ("Typed", parts[0]),
                        ("Corrected", command),
                    ], emoji="✏️")
                else:
                    return False
            else:
                return False

        user_id = message.author.id
        guild_id = message.guild.id

        # Check if in correct channel
        if config.FUN_COMMANDS_CHANNEL_ID and message.channel.id != config.FUN_COMMANDS_CHANNEL_ID:
            embed = discord.Embed(
                description=f"Fun commands only work in <#{config.FUN_COMMANDS_CHANNEL_ID}>",
                color=COLOR_WARNING
            )
            set_footer(embed)
            msg = await message.reply(embed=embed, mention_author=False)
            await msg.delete(delay=DELETE_DELAY_SHORT)
            log.tree("Fun Command Wrong Channel", [
                ("User", f"{message.author.name}"),
                ("ID", str(user_id)),
                ("Command", command),
                ("Channel", message.channel.name if hasattr(message.channel, 'name') else str(message.channel.id)),
            ], emoji="⚠️")
            return True

        # Check cooldown
        last_use = self._cooldowns.get(user_id, 0)
        time_since = time.time() - last_use
        if time_since < self.FUN_COOLDOWN:
            # Calculate when cooldown ends as Discord timestamp
            remaining = self.FUN_COOLDOWN - time_since
            cooldown_ends = int(time.time() + remaining)
            cooldown_msg = await message.reply(
                f"You're on cooldown. Try again <t:{cooldown_ends}:R>",
                mention_author=False
            )
            # Delete both messages after short delay
            await asyncio.gather(
                message.delete(delay=DELETE_DELAY_SHORT),
                cooldown_msg.delete(delay=DELETE_DELAY_SHORT),
                return_exceptions=True
            )
            log.tree("Fun Cooldown", [
                ("User", f"{message.author.name}"),
                ("ID", str(user_id)),
                ("Command", command),
                ("Ends", f"<t:{cooldown_ends}:R>"),
            ], emoji="⏳")
            return True

        # Get server banner
        banner_url = None
        if message.guild and message.guild.banner:
            banner_url = str(message.guild.banner.url)

        # Record cooldown
        self._cooldowns[user_id] = time.time()
        self._cleanup_cooldowns()

        try:
            result = False
            if command == "ship":
                result = await self._handle_ship(message, banner_url)
            elif command == "simp":
                result = await self._handle_simp(message, banner_url)
            elif command == "howgay":
                result = await self._handle_howgay(message, banner_url)
            elif command == "howsmart":
                result = await self._handle_howsmart(message, banner_url)
            elif command == "bodyfat":
                result = await self._handle_bodyfat(message, banner_url)

            # Track message count and send sticky every N messages
            if result:
                self._channel_msg_count += 1
                if self._channel_msg_count >= self.FUN_STICKY_INTERVAL:
                    await self._send_sticky(message.channel)

            return result
        except Exception as e:
            log.error_tree("Fun Command Failed", e, [
                ("Command", command),
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(message.author.id)),
            ])
            embed = discord.Embed(
                description="Failed to generate image. Please try again.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await message.channel.send(embed=embed)
            return True

    async def _handle_ship(self, message: discord.Message, banner_url: str) -> bool:
        """Handle the ship command."""
        # Need exactly 2 mentions
        if len(message.mentions) < 2:
            # If 1 mention, ship author with mentioned user
            if len(message.mentions) == 1:
                user1 = message.author
                user2 = message.mentions[0]
            else:
                log.tree("Ship Usage Error", [
                    ("User", f"{message.author.name}"),
                    ("ID", str(message.author.id)),
                    ("Reason", "No mentions provided"),
                ], emoji="⚠️")
                embed = discord.Embed(
                    description="Usage: `ship @user1 @user2` or `ship @user`",
                    color=COLOR_WARNING
                )
                set_footer(embed)
                msg = await message.channel.send(embed=embed)
                await msg.delete(delay=DELETE_DELAY_SHORT)
                return True
        else:
            user1 = message.mentions[0]
            user2 = message.mentions[1]

        log.tree("Ship Command", [
            ("User", f"{message.author.name}"),
            ("ID", str(message.author.id)),
            ("User 1", f"{user1.name}"),
            ("User 2", f"{user2.name}"),
        ], emoji="💕")

        # Calculate ship
        percentage, ship_message = fun_service.calculate_ship(user1.id, user2.id)
        ship_name = fun_service.get_ship_name(user1.display_name, user2.display_name)

        # Generate card
        async with message.channel.typing():
            card_bytes = await generate_ship_card(
                user1_id=user1.id,
                user1_name=user1.display_name,
                user1_avatar=str(user1.display_avatar.url),
                user2_id=user2.id,
                user2_name=user2.display_name,
                user2_avatar=str(user2.display_avatar.url),
                ship_name=ship_name,
                percentage=percentage,
                message=ship_message,
                banner_url=banner_url,
            )

        file = discord.File(fp=io.BytesIO(card_bytes), filename="ship.png")
        await message.channel.send(file=file)

        log.tree("Ship Sent", [
            ("User 1", f"{user1.name}"),
            ("User 2", f"{user2.name}"),
            ("Result", f"{percentage}%"),
        ], emoji="✅")

        return True

    async def _handle_simp(self, message: discord.Message, banner_url: str) -> bool:
        """Handle the simp command."""
        # Target is mentioned user or author
        if message.mentions:
            target = message.mentions[0]
        else:
            target = message.author

        log.tree("Simp Command", [
            ("User", f"{message.author.name}"),
            ("ID", str(message.author.id)),
            ("Target", f"{target.name}"),
        ], emoji="🥺")

        # Calculate simp level
        percentage, simp_message = fun_service.calculate_simp(target.id, message.guild.id)

        # Generate card
        async with message.channel.typing():
            card_bytes = await generate_meter_card(
                user_id=target.id,
                guild_id=message.guild.id,
                user_name=target.display_name,
                user_avatar=str(target.display_avatar.url),
                percentage=percentage,
                message=simp_message,
                meter_type="simp",
                banner_url=banner_url,
            )

        file = discord.File(fp=io.BytesIO(card_bytes), filename="simp.png")
        await message.channel.send(file=file)

        log.tree("Simp Sent", [
            ("Target", f"{target.name}"),
            ("Result", f"{percentage}%"),
        ], emoji="✅")

        return True

    async def _handle_howgay(self, message: discord.Message, banner_url: str) -> bool:
        """Handle the howgay command."""
        # Target is mentioned user or author
        if message.mentions:
            target = message.mentions[0]
        else:
            target = message.author

        log.tree("Howgay Command", [
            ("User", f"{message.author.name}"),
            ("ID", str(message.author.id)),
            ("Target", f"{target.name}"),
        ], emoji="🌈")

        # Calculate gay level
        percentage, gay_message = fun_service.calculate_gay(target.id, message.guild.id)

        # Generate card
        async with message.channel.typing():
            card_bytes = await generate_meter_card(
                user_id=target.id,
                guild_id=message.guild.id,
                user_name=target.display_name,
                user_avatar=str(target.display_avatar.url),
                percentage=percentage,
                message=gay_message,
                meter_type="gay",
                banner_url=banner_url,
            )

        file = discord.File(fp=io.BytesIO(card_bytes), filename="howgay.png")
        await message.channel.send(file=file)

        log.tree("Howgay Sent", [
            ("Target", f"{target.name}"),
            ("Result", f"{percentage}%"),
        ], emoji="✅")

        return True

    async def _handle_howsmart(self, message: discord.Message, banner_url: str) -> bool:
        """Handle the howsmart command."""
        # Target is mentioned user or author
        if message.mentions:
            target = message.mentions[0]
        else:
            target = message.author

        log.tree("Howsmart Command", [
            ("User", f"{message.author.name}"),
            ("ID", str(message.author.id)),
            ("Target", f"{target.name}"),
        ], emoji="🧠")

        # Calculate smart level
        percentage, smart_message = fun_service.calculate_smart(target.id, message.guild.id)

        # Generate card
        async with message.channel.typing():
            card_bytes = await generate_meter_card(
                user_id=target.id,
                guild_id=message.guild.id,
                user_name=target.display_name,
                user_avatar=str(target.display_avatar.url),
                percentage=percentage,
                message=smart_message,
                meter_type="smart",
                banner_url=banner_url,
            )

        file = discord.File(fp=io.BytesIO(card_bytes), filename="howsmart.png")
        await message.channel.send(file=file)

        log.tree("Howsmart Sent", [
            ("Target", f"{target.name}"),
            ("Result", f"{percentage}%"),
        ], emoji="✅")

        return True

    async def _handle_bodyfat(self, message: discord.Message, banner_url: str) -> bool:
        """Handle the bodyfat command."""
        # Target is mentioned user or author
        if message.mentions:
            target = message.mentions[0]
        else:
            target = message.author

        log.tree("Bodyfat Command", [
            ("User", f"{message.author.name}"),
            ("ID", str(message.author.id)),
            ("Target", f"{target.name}"),
        ], emoji="💪")

        # Calculate body fat
        percentage, bodyfat_message = fun_service.calculate_bodyfat(target.id, message.guild.id)

        # Generate card
        async with message.channel.typing():
            card_bytes = await generate_meter_card(
                user_id=target.id,
                guild_id=message.guild.id,
                user_name=target.display_name,
                user_avatar=str(target.display_avatar.url),
                percentage=percentage,
                message=bodyfat_message,
                meter_type="bodyfat",
                banner_url=banner_url,
            )

        file = discord.File(fp=io.BytesIO(card_bytes), filename="bodyfat.png")
        await message.channel.send(file=file)

        log.tree("Bodyfat Sent", [
            ("Target", f"{target.name}"),
            ("Result", f"{percentage}%"),
        ], emoji="✅")

        return True


# Singleton instance
fun_handler = FunHandler()
