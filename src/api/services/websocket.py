"""
SyriaBot - WebSocket Manager
============================

Real-time server stats and leaderboard broadcasting.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import json
import time
from typing import Set, Dict, Any, Optional, List

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from src.core.logger import logger
from src.utils.async_utils import create_safe_task


class WebSocketManager:
    """Manages WebSocket connections and real-time stats broadcasting."""

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

        # Current stats
        self._stats: Dict[str, int] = {
            "members": 0,
            "online": 0,
            "boosts": 0,
            "messages": 0,
            "ranked": 0,
            "xp": 0,
            "voice_minutes": 0,
            "reactions": 0,
        }

        # Background task for periodic online count updates
        self._online_task: Optional[asyncio.Task] = None
        self._bot = None

        # Cached enriched leaderboard (avoid refetching per connection)
        self._leaderboard_cache: List[Dict[str, Any]] = []
        self._leaderboard_cache_time: float = 0
        _LEADERBOARD_CACHE_TTL = 30  # seconds

    def set_bot(self, bot) -> None:
        """Set bot reference for online count updates."""
        self._bot = bot

    async def start_online_updates(self) -> None:
        """Start periodic online count updates (every 30 seconds)."""
        if self._online_task is not None:
            return

        self._online_task = create_safe_task(self._online_update_loop(), "WS Online Update Loop")
        logger.tree("WebSocket Online Updates", [
            ("Interval", "30 seconds"),
        ], emoji="🟢")

    async def stop_online_updates(self) -> None:
        """Stop periodic online count updates."""
        if self._online_task:
            self._online_task.cancel()
            try:
                await self._online_task
            except asyncio.CancelledError:
                pass
            self._online_task = None

    async def _get_enriched_leaderboard(self) -> List[Dict[str, Any]]:
        """Get enriched leaderboard using CacheService and DiscordService."""
        from src.services.database import db
        from src.api.services.discord import get_discord_service

        try:
            if not self._bot or not self._bot.is_ready():
                return []

            discord_service = get_discord_service(self._bot)

            # Get top 100 from database (run in executor to avoid blocking)
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(
                None, lambda: db.get_leaderboard(limit=100, offset=0)
            )
            if not raw:
                return []

            # Enrich via DiscordService (uses avatar cache internally)
            user_ids = [entry["user_id"] for entry in raw]
            user_data_map = await discord_service.fetch_users_batch(user_ids)

            # Get previous ranks for rank_change calculation
            previous_ranks = await loop.run_in_executor(
                None, lambda: db.get_previous_ranks(user_ids=user_ids)
            )

            enriched = []
            for entry in raw:
                user_id = entry["user_id"]
                user_data = user_data_map.get(user_id)

                if user_data:
                    display_name = user_data.display_name
                    username = user_data.username
                    avatar_url = user_data.avatar_url
                    banner_url = user_data.banner_url
                    is_booster = user_data.is_booster
                else:
                    display_name = str(user_id)
                    username = None
                    avatar_url = None
                    banner_url = None
                    is_booster = False

                # Calculate rank change
                current_rank = entry["rank"]
                rank_change = None
                if previous_ranks and user_id in previous_ranks:
                    rank_change = previous_ranks[user_id] - current_rank

                enriched.append({
                    "user_id": str(user_id),
                    "xp": entry["xp"],
                    "level": entry["level"],
                    "total_messages": entry["total_messages"],
                    "voice_minutes": entry["voice_minutes"],
                    "rank": current_rank,
                    "rank_change": rank_change,
                    "display_name": display_name,
                    "username": username,
                    "avatar": avatar_url,
                    "banner": banner_url,
                    "is_booster": is_booster,
                    "last_active": entry.get("last_active_at") or None,
                    "streak_days": entry.get("streak_days") or 0,
                })

            return enriched
        except Exception as e:
            logger.error_tree("Leaderboard Enrichment Error", e)
            return []

    async def _online_update_loop(self) -> None:
        """Background task to update online count and XP stats every 30 seconds."""
        from src.core.config import config
        from src.services.database import db

        while True:
            try:
                await asyncio.sleep(30)

                if not self._bot or not self._bot.is_ready():
                    continue

                guild = self._bot.get_guild(config.GUILD_ID)
                if not guild:
                    continue

                updates: Dict[str, int] = {}

                # Count online members (not offline, not bots)
                online = sum(
                    1 for m in guild.members
                    if not m.bot and m.status.name != "offline"
                )
                if online != self._stats["online"]:
                    updates["online"] = online

                # Update XP stats (ranked users and total XP)
                try:
                    loop = asyncio.get_event_loop()
                    xp_stats = await loop.run_in_executor(
                        None, lambda: db.get_xp_stats(config.GUILD_ID)
                    )
                    ranked = xp_stats.get("total_users", 0)
                    total_xp = xp_stats.get("total_xp", 0)

                    if ranked != self._stats["ranked"]:
                        updates["ranked"] = ranked
                    if total_xp != self._stats["xp"]:
                        updates["xp"] = total_xp
                except Exception:
                    pass

                # Broadcast all changes at once
                if updates:
                    await self.broadcast_stats(updates)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error_tree("Stats Update Error", e)
                await asyncio.sleep(30)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track a new connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

        # Send current stats immediately
        await self._send_full_stats(websocket)

        # Send leaderboard (use cache to avoid refetching per connection)
        if self._bot and self._bot.is_ready():
            now = time.time()
            if not self._leaderboard_cache or now - self._leaderboard_cache_time > 30:
                self._leaderboard_cache = await self._get_enriched_leaderboard()
                self._leaderboard_cache_time = now
            leaderboard = self._leaderboard_cache
            if leaderboard:
                try:
                    message = json.dumps({
                        "type": "leaderboard",
                        "data": leaderboard
                    })
                    await websocket.send_text(message)
                except Exception:
                    pass

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a connection."""
        async with self._lock:
            self._connections.discard(websocket)

    async def _send_full_stats(self, websocket: WebSocket) -> None:
        """Send all current stats to a single client (includes guild info)."""
        try:
            data = self._stats.copy()

            # Include guild info if bot is ready
            if self._bot and self._bot.is_ready():
                from src.core.config import config
                guild = self._bot.get_guild(config.GUILD_ID)
                if guild:
                    data["guild_name"] = guild.name
                    data["guild_icon"] = str(guild.icon.url) if guild.icon else None
                    data["guild_banner"] = str(guild.banner.url) if guild.banner else None

            message = json.dumps({
                "type": "stats",
                "data": data
            })
            await websocket.send_text(message)
        except Exception:
            pass

    def set_stats(
        self,
        members: int,
        online: int,
        boosts: int,
        messages: int,
        ranked: int = 0,
        xp: int = 0,
        voice_minutes: int = 0,
        reactions: int = 0
    ) -> None:
        """Set all stats at once (used during initialization)."""
        self._stats["members"] = members
        self._stats["online"] = online
        self._stats["boosts"] = boosts
        self._stats["messages"] = messages
        self._stats["ranked"] = ranked
        self._stats["xp"] = xp
        self._stats["voice_minutes"] = voice_minutes
        self._stats["reactions"] = reactions

    def set_stat(self, key: str, value: int) -> None:
        """Set a single stat without broadcasting."""
        if key in self._stats:
            self._stats[key] = value

    async def broadcast_stat(self, key: str, value: int) -> None:
        """Broadcast a single stat update to all clients."""
        if key not in self._stats:
            return

        self._stats[key] = value

        if not self._connections:
            return

        message = json.dumps({
            "type": "stat_update",
            "data": {key: value}
        })

        await self._broadcast(message)

    async def broadcast_stats(self, updates: Dict[str, int]) -> None:
        """Broadcast multiple stat updates at once."""
        for key, value in updates.items():
            if key in self._stats:
                self._stats[key] = value

        if not self._connections:
            return

        message = json.dumps({
            "type": "stat_update",
            "data": updates
        })

        await self._broadcast(message)

    async def broadcast_leaderboard_update(self, updates: List[Dict[str, Any]]) -> None:
        """Broadcast leaderboard changes to all clients."""
        if not self._connections:
            return

        message = json.dumps({
            "type": "leaderboard_update",
            "data": {"updates": updates}
        })

        await self._broadcast(message)

    async def _broadcast(self, message: str) -> None:
        """Broadcast a message to all connected clients in parallel."""
        # Snapshot connections under lock, then release before sending
        async with self._lock:
            if not self._connections:
                return
            connections = list(self._connections)

        # Send to all connections in parallel
        async def send_safe(ws: WebSocket) -> Optional[WebSocket]:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
                    return None
                return ws  # Dead connection
            except Exception:
                return ws  # Failed connection

        results = await asyncio.gather(
            *[send_safe(ws) for ws in connections],
            return_exceptions=True
        )

        # Collect dead connections
        dead = {r for r in results if isinstance(r, WebSocket)}
        if dead:
            async with self._lock:
                self._connections -= dead

    # Increment methods for real-time updates
    async def increment_xp(self, amount: int) -> None:
        """Increment total XP counter and broadcast."""
        self._stats["xp"] += amount
        await self.broadcast_stat("xp", self._stats["xp"])

    async def increment_ranked(self) -> None:
        """Increment ranked users counter and broadcast."""
        self._stats["ranked"] += 1
        await self.broadcast_stat("ranked", self._stats["ranked"])

    async def increment_reactions(self) -> None:
        """Increment reactions counter and broadcast."""
        self._stats["reactions"] += 1
        await self.broadcast_stat("reactions", self._stats["reactions"])

    async def increment_voice_minutes(self, amount: int = 1) -> None:
        """Increment voice minutes counter and broadcast."""
        self._stats["voice_minutes"] += amount
        await self.broadcast_stat("voice_minutes", self._stats["voice_minutes"])

    # Legacy methods for backwards compatibility
    def set_message_count(self, count: int) -> None:
        """Set message count (legacy method)."""
        self._stats["messages"] = count

    async def broadcast_message_count(self, count: int) -> None:
        """Broadcast message count (legacy method)."""
        await self.broadcast_stat("messages", count)

    @property
    def message_count(self) -> int:
        """Get current message count."""
        return self._stats["messages"]

    @property
    def stats(self) -> Dict[str, int]:
        """Get all current stats."""
        return self._stats.copy()

    @property
    def connection_count(self) -> int:
        """Get current connection count."""
        return len(self._connections)

    # Bot log and status broadcasting
    async def broadcast_bot_log(self, log_data: Dict[str, Any]) -> None:
        """Broadcast a bot log entry to all connected clients."""
        if not self._connections:
            return

        message = json.dumps({
            "type": "bot_log",
            "data": log_data
        })

        await self._broadcast(message)

    async def broadcast_bot_status(self, status_data: Dict[str, Any]) -> None:
        """Broadcast bot status update to all connected clients."""
        if not self._connections:
            return

        message = json.dumps({
            "type": "bot_status",
            "data": status_data
        })

        await self._broadcast(message)

    async def broadcast_discord_event(self, event_data: Dict[str, Any]) -> None:
        """Broadcast a Discord event to all connected clients."""
        if not self._connections:
            return

        message = json.dumps({
            "type": "discord_event",
            "data": event_data
        })

        await self._broadcast(message)


# Singleton
_ws_manager: WebSocketManager | None = None


def get_ws_manager() -> WebSocketManager:
    """Get WebSocket manager singleton."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager


__all__ = ["WebSocketManager", "get_ws_manager"]
