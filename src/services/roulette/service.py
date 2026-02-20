"""
SyriaBot - Roulette Service
===========================

Main service for the roulette minigame.
Handles random spawning, game state, and XP rewards.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import io
import random
import time
import uuid
from collections import deque
from typing import Dict, List, Optional, Set, TYPE_CHECKING

import discord

from src.core.config import config
from src.core.logger import logger
from src.services.database import db

from .graphics import RoulettePlayer, generate_wheel_static, generate_wheel_result
from .views import (
    RouletteJoinView,
    create_join_embed,
    create_spinning_embed,
    create_winner_embed,
    create_cancelled_embed,
)

if TYPE_CHECKING:
    from src.bot import SyriaBot


# Configuration
MIN_PLAYERS = 3
JOIN_DURATION = 60  # seconds (increased for rare event)
XP_REWARD = 1000
MIN_SPAWN_INTERVAL = 3 * 60 * 60  # 3 hours
MAX_SPAWN_INTERVAL = 6 * 60 * 60  # 6 hours

# Activity detection
ACTIVITY_WINDOW = 15 * 60  # 15 minutes - how far back to check for activity
ACTIVITY_MIN_MESSAGES = 5  # minimum messages in window to consider chat "active"
ACTIVITY_RETRY_DELAY = 10 * 60  # 10 minutes - retry if chat is dead


class RouletteGame:
    """
    Represents an active roulette game.

    Tracks players, game state, and handles the spin/reveal flow.
    """

    def __init__(self, channel: discord.TextChannel, bot: "SyriaBot") -> None:
        self.game_id: str = str(uuid.uuid4())[:8]
        self.channel: discord.TextChannel = channel
        self.bot: "SyriaBot" = bot

        # Player tracking
        self.player_ids: Set[int] = set()
        self.players: List[Dict] = []  # [{user_id, display_name, avatar_url}]

        # Game state
        self.is_spinning: bool = False
        self.is_finished: bool = False
        self.winner_id: Optional[int] = None

        # Message reference
        self.message: Optional[discord.Message] = None
        self.view: Optional[RouletteJoinView] = None

    async def start(self) -> bool:
        """
        Start the join phase.

        Returns True if game started successfully.
        """
        try:
            # Create initial embed and view
            embed = create_join_embed(
                player_count=0,
                time_remaining=JOIN_DURATION,
                min_players=MIN_PLAYERS,
                xp_reward=XP_REWARD,
            )

            self.view = RouletteJoinView(self)

            # Send the join message
            self.message = await self.channel.send(
                embed=embed,
                view=self.view,
            )

            logger.tree("Roulette Game Started", [
                ("Game ID", self.game_id),
                ("Channel", self.channel.name),
                ("Channel ID", str(self.channel.id)),
                ("Join Duration", f"{JOIN_DURATION}s"),
            ], emoji="🎰")

            # Start countdown
            asyncio.create_task(self._run_join_phase())

            return True

        except discord.HTTPException as e:
            logger.tree("Roulette Start Failed", [
                ("Game ID", self.game_id),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False

    async def _run_join_phase(self) -> None:
        """Run the join phase with countdown updates."""
        try:
            # Update embed every 10 seconds
            intervals = [20, 10, 5, 3, 2, 1]
            elapsed = 0

            for i, wait_time in enumerate([10, 10, 5, 2, 1, 1, 1]):
                if elapsed >= JOIN_DURATION:
                    break

                await asyncio.sleep(wait_time)
                elapsed += wait_time

                if self.is_finished:
                    return

                # Update embed with new time
                remaining = max(0, JOIN_DURATION - elapsed)
                if self.message:
                    try:
                        embed = create_join_embed(
                            player_count=len(self.players),
                            time_remaining=remaining,
                            min_players=MIN_PLAYERS,
                            xp_reward=XP_REWARD,
                        )
                        await self.message.edit(embed=embed)
                    except discord.HTTPException:
                        pass

            # Join phase ended - check if enough players
            await self._end_join_phase()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error_tree("Roulette Join Phase Error", e, [
                ("Game ID", self.game_id),
            ])

    async def _end_join_phase(self) -> None:
        """End the join phase and either spin or cancel."""
        if self.is_finished:
            return

        logger.tree("Roulette Join Phase Ended", [
            ("Game ID", self.game_id),
            ("Total Players", str(len(self.players))),
            ("Min Required", str(MIN_PLAYERS)),
            ("Player Names", ", ".join(p["display_name"] for p in self.players) if self.players else "None"),
        ], emoji="⏱️")

        # Disable join button
        if self.view:
            for item in self.view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            try:
                if self.message:
                    await self.message.edit(view=self.view)
            except discord.HTTPException:
                pass

        # Check player count
        if len(self.players) < MIN_PLAYERS:
            await self._cancel(
                f"Not enough players joined ({len(self.players)}/{MIN_PLAYERS} needed)"
            )
            return

        # Start the spin!
        await self._spin()

    async def _spin(self) -> None:
        """Execute the wheel spin and reveal winner."""
        self.is_spinning = True

        logger.tree("Roulette Spinning", [
            ("Game ID", self.game_id),
            ("Players", str(len(self.players))),
            ("Player Names", ", ".join(p["display_name"] for p in self.players)),
        ], emoji="🎯")

        # Select random winner
        winner_index = random.randint(0, len(self.players) - 1)
        winner_data = self.players[winner_index]
        self.winner_id = winner_data["user_id"]

        try:
            # Update message to spinning state
            spinning_embed = create_spinning_embed()
            if self.message:
                await self.message.edit(embed=spinning_embed, view=None)

            # Generate wheel result image
            roulette_players = [
                RoulettePlayer(
                    user_id=p["user_id"],
                    display_name=p["display_name"],
                    avatar_url=p["avatar_url"],
                )
                for p in self.players
            ]

            result_image = await generate_wheel_result(roulette_players, winner_index)

            # Add dramatic delay
            await asyncio.sleep(2)

            # Get winner member
            winner = self.channel.guild.get_member(self.winner_id)
            if not winner:
                logger.tree("Roulette Winner Not Found", [
                    ("Game ID", self.game_id),
                    ("Winner ID", str(self.winner_id)),
                ], emoji="⚠️")
                await self._cancel("Winner left the server!")
                return

            # Award XP
            try:
                db.add_xp(self.winner_id, self.channel.guild.id, XP_REWARD, "roulette")
                logger.tree("Roulette XP Awarded", [
                    ("Game ID", self.game_id),
                    ("Winner", f"{winner.name} ({winner.display_name})"),
                    ("Winner ID", str(self.winner_id)),
                    ("XP", str(XP_REWARD)),
                ], emoji="⬆️")
            except Exception as e:
                logger.error_tree("Roulette XP Award Failed", e, [
                    ("Game ID", self.game_id),
                    ("Winner ID", str(self.winner_id)),
                ])

            # Create winner embed
            winner_embed = create_winner_embed(
                winner=winner,
                xp_awarded=XP_REWARD,
                player_count=len(self.players),
            )

            # Send result with image
            file = discord.File(
                io.BytesIO(result_image),
                filename="roulette_result.png"
            )
            winner_embed.set_image(url="attachment://roulette_result.png")

            if self.message:
                await self.message.edit(
                    content=f"Congratulations {winner.mention}!",
                    embed=winner_embed,
                    attachments=[file],
                    view=None,
                )

            self.is_finished = True

            logger.tree("Roulette Complete", [
                ("Game ID", self.game_id),
                ("Winner", f"{winner.name} ({winner.display_name})"),
                ("Winner ID", str(self.winner_id)),
                ("Players", str(len(self.players))),
                ("XP Awarded", str(XP_REWARD)),
            ], emoji="🎉")

        except Exception as e:
            logger.error_tree("Roulette Spin Failed", e, [
                ("Game ID", self.game_id),
            ])
            self.is_finished = True

    async def _cancel(self, reason: str) -> None:
        """Cancel the game."""
        self.is_finished = True

        logger.tree("Roulette Cancelled", [
            ("Game ID", self.game_id),
            ("Reason", reason),
            ("Players", str(len(self.players))),
        ], emoji="🚫")

        try:
            embed = create_cancelled_embed(reason)
            if self.message:
                await self.message.edit(
                    content=None,
                    embed=embed,
                    view=None,
                )
        except discord.HTTPException as e:
            logger.tree("Roulette Cancel Edit Failed", [
                ("Game ID", self.game_id),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    async def update_join_embed(self) -> None:
        """Update the join embed with current player count."""
        if self.is_finished or self.is_spinning:
            return

        try:
            if self.message:
                embed = create_join_embed(
                    player_count=len(self.players),
                    time_remaining=JOIN_DURATION,  # Approximate
                    min_players=MIN_PLAYERS,
                    xp_reward=XP_REWARD,
                )
                await self.message.edit(embed=embed)
        except discord.HTTPException:
            pass


class RouletteService:
    """
    Main roulette service.

    Handles random spawn timing and game management.
    Tracks chat activity to only spawn when chat is active.
    """

    def __init__(self, bot: "SyriaBot") -> None:
        self.bot = bot
        self._spawn_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._current_game: Optional[RouletteGame] = None
        # Activity tracking - stores timestamps of recent messages
        self._message_timestamps: deque = deque(maxlen=100)

    def on_message(self, message: discord.Message) -> None:
        """Track message activity in general channel."""
        # Only track general channel messages
        if message.channel.id != config.GENERAL_CHANNEL_ID:
            return
        # Ignore bot messages
        if message.author.bot:
            return
        # Store timestamp
        self._message_timestamps.append(time.time())

    def _is_chat_active(self) -> tuple[bool, int]:
        """
        Check if chat is active enough to spawn a roulette.

        Returns:
            Tuple of (is_active, message_count_in_window)
        """
        now = time.time()
        cutoff = now - ACTIVITY_WINDOW

        # Count messages within the activity window
        recent_count = sum(1 for ts in self._message_timestamps if ts > cutoff)

        return recent_count >= ACTIVITY_MIN_MESSAGES, recent_count

    async def setup(self) -> None:
        """Start the roulette spawn timer."""
        self._running = True
        self._spawn_task = asyncio.create_task(self._spawn_loop())

        logger.tree("Roulette Service Started", [
            ("Min Interval", f"{MIN_SPAWN_INTERVAL // 3600}h"),
            ("Max Interval", f"{MAX_SPAWN_INTERVAL // 3600}h"),
            ("XP Reward", f"{XP_REWARD:,}"),
            ("Min Players", str(MIN_PLAYERS)),
            ("Join Duration", f"{JOIN_DURATION}s"),
            ("Activity Window", f"{ACTIVITY_WINDOW // 60}m"),
            ("Activity Threshold", f"{ACTIVITY_MIN_MESSAGES} msgs"),
            ("Channel", str(config.GENERAL_CHANNEL_ID)),
        ], emoji="🎰")

    def stop(self) -> None:
        """Stop the roulette service."""
        self._running = False
        if self._spawn_task:
            self._spawn_task.cancel()

        logger.tree("Roulette Service Stopped", [], emoji="🛑")

    async def _spawn_loop(self) -> None:
        """Background loop that spawns roulette games at random intervals."""
        await self.bot.wait_until_ready()

        # Initial delay before first game (5-10 minutes)
        initial_delay = random.randint(5 * 60, 10 * 60)
        logger.tree("Roulette First Spawn Scheduled", [
            ("Delay", f"{initial_delay // 60} min"),
        ], emoji="⏰")
        await asyncio.sleep(initial_delay)

        while self._running:
            try:
                # Try to spawn a game
                spawned = await self._spawn_game()

                if spawned:
                    # Game spawned (or skipped for valid reason) - wait full interval
                    next_interval = random.randint(MIN_SPAWN_INTERVAL, MAX_SPAWN_INTERVAL)
                    hours = next_interval // 3600
                    mins = (next_interval % 3600) // 60
                    logger.tree("Roulette Next Spawn Scheduled", [
                        ("Delay", f"{hours}h {mins}m"),
                        ("Seconds", str(next_interval)),
                    ], emoji="⏰")
                    await asyncio.sleep(next_interval)
                else:
                    # Chat was dead - retry after shorter delay
                    logger.tree("Roulette Retry Scheduled", [
                        ("Delay", f"{ACTIVITY_RETRY_DELAY // 60}m"),
                        ("Reason", "Waiting for chat activity"),
                    ], emoji="🔄")
                    await asyncio.sleep(ACTIVITY_RETRY_DELAY)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error_tree("Roulette Spawn Loop Error", e)
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def _spawn_game(self) -> bool:
        """
        Spawn a new roulette game in general chat.

        Returns:
            True if game spawned, False if skipped (will retry later)
        """
        # Don't spawn if a game is already running
        if self._current_game and not self._current_game.is_finished:
            logger.tree("Roulette Spawn Skipped", [
                ("Reason", "Game already active"),
                ("Active Game ID", self._current_game.game_id),
            ], emoji="⏭️")
            return True  # Don't retry, game is running

        # Check if chat is active
        is_active, msg_count = self._is_chat_active()
        if not is_active:
            logger.tree("Roulette Spawn Delayed", [
                ("Reason", "Chat is dead"),
                ("Messages in Window", str(msg_count)),
                ("Required", str(ACTIVITY_MIN_MESSAGES)),
                ("Window", f"{ACTIVITY_WINDOW // 60}m"),
                ("Retry In", f"{ACTIVITY_RETRY_DELAY // 60}m"),
            ], emoji="💤")
            return False  # Signal to retry later

        # Get general channel
        channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.tree("Roulette Spawn Failed", [
                ("Reason", "General channel not found"),
                ("Channel ID", str(config.GENERAL_CHANNEL_ID)),
            ], emoji="❌")
            return True  # Don't retry, config issue

        logger.tree("Roulette Spawning", [
            ("Channel", channel.name),
            ("Channel ID", str(channel.id)),
            ("Guild", channel.guild.name),
            ("XP Prize", f"{XP_REWARD:,}"),
            ("Chat Activity", f"{msg_count} msgs in {ACTIVITY_WINDOW // 60}m"),
        ], emoji="🎲")

        # Create and start game
        game = RouletteGame(channel, self.bot)
        self._current_game = game

        success = await game.start()
        if not success:
            self._current_game = None
            logger.tree("Roulette Spawn Failed", [
                ("Reason", "Game start returned false"),
                ("Game ID", game.game_id),
            ], emoji="❌")

        return True  # Game attempted, don't retry

    async def force_spawn(self, channel: discord.TextChannel) -> Optional[RouletteGame]:
        """
        Force spawn a roulette game in a specific channel.
        Used for testing/admin commands.

        Returns the game if started successfully, None otherwise.
        """
        # Don't spawn if a game is already running
        if self._current_game and not self._current_game.is_finished:
            return None

        game = RouletteGame(channel, self.bot)
        self._current_game = game

        success = await game.start()
        if success:
            return game
        else:
            self._current_game = None
            return None


# Singleton instance
_service: Optional[RouletteService] = None


def get_roulette_service(bot: Optional["SyriaBot"] = None) -> RouletteService:
    """Get or create the roulette service singleton."""
    global _service
    if _service is None:
        if bot is None:
            raise ValueError("Bot required for first initialization")
        _service = RouletteService(bot)
    return _service
