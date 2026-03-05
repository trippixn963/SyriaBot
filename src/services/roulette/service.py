"""
SyriaBot - Roulette Service
===========================

Automatic roulette minigame.
Participants are selected from recent message activity — no join button.
Users who sent more messages get a bigger wheel slice and higher win chance.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import io
import random
import uuid
from typing import Dict, List, Optional, TYPE_CHECKING

import discord

from src.core.config import config
from src.core.logger import logger
from src.services.database import db

from .graphics import RoulettePlayer, generate_wheel_result
from .views import (
    create_announcement_embed,
    create_spinning_embed,
    create_winner_embed,
    create_cancelled_embed,
)

if TYPE_CHECKING:
    from src.bot import SyriaBot


# Configuration
MIN_PLAYERS = 3
MAX_PLAYERS = 10
XP_REWARD = 1000
MIN_SPAWN_INTERVAL = 3 * 60 * 60  # 3 hours
MAX_SPAWN_INTERVAL = 6 * 60 * 60  # 6 hours
MIN_SEGMENT_WEIGHT = 0.05  # 5% minimum slice

# Activity detection
ACTIVITY_RETRY_DELAY = 10 * 60  # 10 minutes - retry if not enough users


class RouletteService:
    """
    Automatic roulette service.

    Tracks per-user message counts in general chat since the last roulette.
    When triggered, selects top 10 most active users, spins a weighted wheel.
    """

    def __init__(self, bot: "SyriaBot") -> None:
        self.bot = bot
        self._spawn_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._game_running: bool = False

        # Per-user activity tracking since last roulette
        # {user_id: {name: str, avatar_url: str, count: int}}
        self._user_activity: Dict[int, Dict] = {}

    def on_message(self, message: discord.Message) -> None:
        """Track message activity in general channel."""
        if message.channel.id != config.GENERAL_CHANNEL_ID:
            return
        if message.author.bot:
            return

        uid = message.author.id
        if uid in self._user_activity:
            self._user_activity[uid]["count"] += 1
            # Update name/avatar in case they changed
            self._user_activity[uid]["name"] = message.author.display_name
            self._user_activity[uid]["avatar_url"] = message.author.display_avatar.url
        else:
            self._user_activity[uid] = {
                "name": message.author.display_name,
                "avatar_url": message.author.display_avatar.url,
                "count": 1,
            }

    def _is_chat_active(self) -> tuple[bool, int]:
        """
        Check if enough unique users have chatted since last roulette.

        Returns:
            Tuple of (has_enough_users, unique_user_count)
        """
        unique_users = len(self._user_activity)
        return unique_users >= MIN_PLAYERS, unique_users

    async def setup(self) -> None:
        """Start the roulette spawn timer."""
        self._running = True
        self._spawn_task = asyncio.create_task(self._spawn_loop())

        logger.tree("Roulette Service Started", [
            ("Min Interval", f"{MIN_SPAWN_INTERVAL // 3600}h"),
            ("Max Interval", f"{MAX_SPAWN_INTERVAL // 3600}h"),
            ("XP Reward", f"{XP_REWARD:,}"),
            ("Min Players", str(MIN_PLAYERS)),
            ("Max Players", str(MAX_PLAYERS)),
            ("Mode", "Automatic (activity-based)"),
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

        # Initial delay before first game (same 3-6hr range)
        initial_delay = random.randint(MIN_SPAWN_INTERVAL, MAX_SPAWN_INTERVAL)
        hours = initial_delay // 3600
        mins = (initial_delay % 3600) // 60
        logger.tree("Roulette First Spawn Scheduled", [
            ("Delay", f"{hours}h {mins}m"),
        ], emoji="⏰")
        await asyncio.sleep(initial_delay)

        while self._running:
            try:
                spawned = await self._try_spawn()

                if spawned:
                    # Game ran — wait full interval before next
                    next_interval = random.randint(MIN_SPAWN_INTERVAL, MAX_SPAWN_INTERVAL)
                    hours = next_interval // 3600
                    mins = (next_interval % 3600) // 60
                    logger.tree("Roulette Next Spawn Scheduled", [
                        ("Delay", f"{hours}h {mins}m"),
                        ("Seconds", str(next_interval)),
                    ], emoji="⏰")
                    await asyncio.sleep(next_interval)
                else:
                    # Not enough users — retry after shorter delay
                    logger.tree("Roulette Retry Scheduled", [
                        ("Delay", f"{ACTIVITY_RETRY_DELAY // 60}m"),
                        ("Reason", "Waiting for more active users"),
                    ], emoji="🔄")
                    await asyncio.sleep(ACTIVITY_RETRY_DELAY)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error_tree("Roulette Spawn Loop Error", e)
                await asyncio.sleep(60)

    async def _try_spawn(self) -> bool:
        """
        Try to spawn a roulette in general chat.

        Returns True if game ran, False if not enough users.
        """
        if self._game_running:
            return True  # Don't retry, game is active

        # Check if enough unique users
        is_active, user_count = self._is_chat_active()
        if not is_active:
            total_msgs = sum(d["count"] for d in self._user_activity.values())
            logger.tree("Roulette Spawn Delayed", [
                ("Reason", "Not enough active users"),
                ("Unique Users", str(user_count)),
                ("Total Messages", str(total_msgs)),
                ("Required", f"{MIN_PLAYERS} unique users"),
                ("Retry In", f"{ACTIVITY_RETRY_DELAY // 60}m"),
            ], emoji="💤")
            return False

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
            ("Active Users", str(user_count)),
            ("XP Prize", f"{XP_REWARD:,}"),
        ], emoji="🎲")

        await self._run_roulette(channel)
        return True

    async def _run_roulette(
        self,
        channel: discord.TextChannel,
        min_players: int = MIN_PLAYERS,
    ) -> None:
        """
        Execute a full roulette game: announce → spin → reveal.

        Args:
            channel: Channel to run the game in
            min_players: Minimum players required (lowered for force_spawn)
        """
        self._game_running = True
        game_id = str(uuid.uuid4())[:8]

        try:
            # 1. Snapshot and reset activity immediately so messages
            #    during the game count toward the next roulette
            activity_snapshot = dict(self._user_activity)
            self._user_activity.clear()

            # 2. Filter out users who left the server
            guild = channel.guild
            activity_snapshot = {
                uid: data for uid, data in activity_snapshot.items()
                if guild.get_member(uid) is not None
            }

            # 3. Collect top players sorted by message count
            sorted_users = sorted(
                activity_snapshot.items(),
                key=lambda x: x[1]["count"],
                reverse=True,
            )[:MAX_PLAYERS]

            if len(sorted_users) < min_players:
                logger.tree("Roulette Cancelled", [
                    ("Game ID", game_id),
                    ("Reason", f"Only {len(sorted_users)} users (need {min_players})"),
                    ("Users", ", ".join(d["name"] for _, d in sorted_users) or "None"),
                ], emoji="🚫")
                return

            # 3. Calculate weights
            total_messages = sum(data["count"] for _, data in sorted_users)
            raw_weights = [data["count"] / total_messages for _, data in sorted_users]

            # Enforce 5% minimum segment
            weights = self._enforce_min_weights(raw_weights)

            # 4. Build player list
            players: List[RoulettePlayer] = []
            for i, (uid, data) in enumerate(sorted_users):
                players.append(RoulettePlayer(
                    user_id=uid,
                    display_name=data["name"],
                    avatar_url=data["avatar_url"],
                    weight=weights[i],
                    message_count=data["count"],
                ))

            logger.tree("Roulette Game Started", [
                ("Game ID", game_id),
                ("Channel", channel.name),
                ("Players", str(len(players))),
                ("Total Messages", str(total_messages)),
                ("Player List", ", ".join(
                    f"{p.display_name} ({p.message_count} msgs, {p.weight*100:.1f}%)"
                    for p in players
                )),
            ], emoji="🎰")

            # 5. Weighted random selection
            winner_index = random.choices(
                range(len(players)),
                weights=[p.weight for p in players],
            )[0]
            winner_player = players[winner_index]

            logger.tree("Roulette Winner Selected", [
                ("Game ID", game_id),
                ("Winner", winner_player.display_name),
                ("Winner ID", str(winner_player.user_id)),
                ("Messages", str(winner_player.message_count)),
                ("Win Probability", f"{winner_player.weight * 100:.1f}%"),
            ], emoji="🎯")

            # 6. Send announcement embed
            announcement_embed = create_announcement_embed(players, XP_REWARD)

            try:
                msg = await channel.send(embed=announcement_embed)
            except discord.HTTPException as e:
                logger.error_tree("Roulette Announcement Send Failed", e, [
                    ("Game ID", game_id),
                    ("Channel", channel.name),
                    ("Channel ID", str(channel.id)),
                ])
                return

            # 7. Generate wheel image (happens while users read announcement)
            try:
                guild_icon = channel.guild.icon.url if channel.guild.icon else None
                result_image = await generate_wheel_result(players, winner_index, guild_icon_url=guild_icon)
            except Exception as e:
                logger.error_tree("Roulette Wheel Generation Failed", e, [
                    ("Game ID", game_id),
                    ("Players", str(len(players))),
                ])
                try:
                    await msg.edit(embed=create_cancelled_embed("Wheel generation failed"))
                except discord.HTTPException:
                    pass
                return

            # 8. Transition to spinning state
            try:
                await msg.edit(embed=create_spinning_embed())
            except discord.HTTPException as e:
                logger.error_tree("Roulette Spinning Edit Failed", e, [
                    ("Game ID", game_id),
                ])

            # 9. Dramatic delay
            await asyncio.sleep(3)

            # 10. Get winner member
            winner = channel.guild.get_member(winner_player.user_id)
            if not winner:
                logger.tree("Roulette Winner Not Found", [
                    ("Game ID", game_id),
                    ("Winner", winner_player.display_name),
                    ("Winner ID", str(winner_player.user_id)),
                ], emoji="⚠️")
                try:
                    await msg.edit(embed=create_cancelled_embed("Winner left the server!"))
                except discord.HTTPException:
                    pass
                return

            # 11. Award XP
            try:
                await asyncio.to_thread(db.add_xp, winner_player.user_id, channel.guild.id, XP_REWARD, "roulette")
                logger.tree("Roulette XP Awarded", [
                    ("Game ID", game_id),
                    ("Winner", f"{winner.name} ({winner.display_name})"),
                    ("Winner ID", str(winner_player.user_id)),
                    ("XP", str(XP_REWARD)),
                ], emoji="⬆️")
            except Exception as e:
                logger.error_tree("Roulette XP Award Failed", e, [
                    ("Game ID", game_id),
                    ("Winner", winner_player.display_name),
                    ("Winner ID", str(winner_player.user_id)),
                    ("XP Amount", str(XP_REWARD)),
                ])

            # 12. Reveal winner with wheel image
            winner_embed = create_winner_embed(
                winner=winner,
                xp_awarded=XP_REWARD,
                player_count=len(players),
                message_count=winner_player.message_count,
                win_probability=winner_player.weight * 100,
            )

            file = discord.File(
                io.BytesIO(result_image),
                filename="roulette_result.png",
            )
            winner_embed.set_image(url="attachment://roulette_result.png")

            try:
                await msg.edit(
                    content=f"Congratulations {winner.mention}!",
                    embed=winner_embed,
                    attachments=[file],
                )
            except discord.HTTPException as e:
                logger.error_tree("Roulette Result Edit Failed", e, [
                    ("Game ID", game_id),
                    ("Winner", winner_player.display_name),
                    ("Winner ID", str(winner_player.user_id)),
                ])

            logger.tree("Roulette Complete", [
                ("Game ID", game_id),
                ("Winner", f"{winner.name} ({winner.display_name})"),
                ("Winner ID", str(winner_player.user_id)),
                ("Winner Messages", str(winner_player.message_count)),
                ("Win Probability", f"{winner_player.weight * 100:.1f}%"),
                ("Players", str(len(players))),
                ("Total Messages", str(total_messages)),
                ("XP Awarded", str(XP_REWARD)),
            ], emoji="🎉")

        except Exception as e:
            logger.error_tree("Roulette Game Error", e, [
                ("Game ID", game_id),
                ("Channel", channel.name),
                ("Channel ID", str(channel.id)),
            ])
        finally:
            self._game_running = False

    @staticmethod
    def _enforce_min_weights(weights: List[float]) -> List[float]:
        """
        Enforce minimum 5% segment for all players.
        Redistributes excess proportionally from larger segments.
        """
        n = len(weights)
        min_w = MIN_SEGMENT_WEIGHT

        # If all equal or below min, just make equal
        if n * min_w >= 1.0:
            return [1.0 / n] * n

        result = list(weights)
        # Find segments below minimum and boost them
        deficit = 0.0
        above_min = []
        for i, w in enumerate(result):
            if w < min_w:
                deficit += min_w - w
                result[i] = min_w
            else:
                above_min.append(i)

        # Redistribute deficit from segments above minimum
        if above_min and deficit > 0:
            total_above = sum(result[i] for i in above_min)
            for i in above_min:
                result[i] -= deficit * (result[i] / total_above)

        # Normalize to exactly 1.0
        total = sum(result)
        if total > 0:
            result = [w / total for w in result]

        return result

    async def force_spawn(self, channel: discord.TextChannel) -> bool:
        """
        Force spawn a roulette game in a specific channel.
        Used for testing/admin commands. Bypasses MIN_PLAYERS (needs at least 1).

        Returns True if game started, False if blocked.
        """
        if self._game_running:
            logger.tree("Roulette Force Spawn Blocked", [
                ("Reason", "Game already running"),
                ("Channel", channel.name),
            ], emoji="⚠️")
            return False

        if len(self._user_activity) == 0:
            logger.tree("Roulette Force Spawn Failed", [
                ("Reason", "No active users to select from"),
                ("Channel", channel.name),
            ], emoji="❌")
            return False

        logger.tree("Roulette Force Spawn", [
            ("Channel", channel.name),
            ("Active Users", str(len(self._user_activity))),
            ("Total Messages", str(sum(d["count"] for d in self._user_activity.values()))),
        ], emoji="⚡")

        # Use min_players=1 to bypass the normal minimum
        await self._run_roulette(channel, min_players=1)
        return True


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
