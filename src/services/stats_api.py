"""
SyriaBot - Stats API
====================

HTTP API server for SyriaBot XP Leaderboard Dashboard.

Exposes XP stats, leaderboard, and user data.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import time
from collections import defaultdict
from datetime import datetime
from aiohttp import web
from typing import TYPE_CHECKING, Optional

from src.core.logger import log
from src.core.constants import (
    STATS_API_PORT,
    STATS_API_HOST,
    TIMEZONE_DAMASCUS,
    TIMEZONE_EST,
)
from src.services.database import db

if TYPE_CHECKING:
    from src.bot import SyriaBot

# Aliases for backwards compatibility
DAMASCUS_TZ = TIMEZONE_DAMASCUS


# =============================================================================
# Rate Limiting
# =============================================================================

class RateLimiter:
    """Simple in-memory rate limiter using sliding window."""

    def __init__(self, requests_per_minute: int = 60, burst_limit: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_ip: str) -> tuple[bool, Optional[int]]:
        """Check if request is allowed for this IP."""
        async with self._lock:
            now = time.time()
            window_start = now - 60

            # Clean old requests
            self._requests[client_ip] = [
                ts for ts in self._requests[client_ip]
                if ts > window_start
            ]

            requests = self._requests[client_ip]

            # Check per-minute limit
            if len(requests) >= self.requests_per_minute:
                oldest = min(requests) if requests else now
                retry_after = int(oldest + 60 - now) + 1
                return False, retry_after

            # Check burst limit (last 1 second)
            recent = [ts for ts in requests if ts > now - 1]
            if len(recent) >= self.burst_limit:
                return False, 1

            # Allow request
            self._requests[client_ip].append(now)
            return True, None

    async def cleanup(self) -> None:
        """Remove stale entries older than 2 minutes."""
        async with self._lock:
            cutoff = time.time() - 120
            stale_ips = [
                ip for ip, timestamps in self._requests.items()
                if not timestamps or max(timestamps) < cutoff
            ]
            for ip in stale_ips:
                del self._requests[ip]


# Global rate limiter
rate_limiter = RateLimiter(requests_per_minute=60, burst_limit=10)


# =============================================================================
# Security Middleware
# =============================================================================

def get_client_ip(request: web.Request) -> str:
    """Extract client IP from request, handling proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    peername = request.transport.get_extra_info("peername")
    if peername:
        return peername[0]

    return "unknown"


@web.middleware
async def rate_limit_middleware(request: web.Request, handler) -> web.Response:
    """Middleware to enforce rate limiting on all requests."""
    if request.path == "/health":
        return await handler(request)

    client_ip = get_client_ip(request)
    allowed, retry_after = await rate_limiter.is_allowed(client_ip)

    if not allowed:
        log.tree("Rate Limit Exceeded", [
            ("IP", client_ip),
            ("Path", request.path),
            ("Retry-After", f"{retry_after}s"),
        ], emoji="⚠️")
        return web.json_response(
            {"error": "Rate limit exceeded", "retry_after": retry_after},
            status=429,
            headers={
                "Retry-After": str(retry_after),
                "Access-Control-Allow-Origin": "*",
            }
        )

    return await handler(request)


@web.middleware
async def cors_middleware(request: web.Request, handler) -> web.Response:
    """Middleware to add CORS headers to all responses."""
    # Handle preflight OPTIONS requests
    if request.method == "OPTIONS":
        return web.Response(
            status=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Max-Age": "86400",
            }
        )

    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    return response


@web.middleware
async def security_headers_middleware(request: web.Request, handler) -> web.Response:
    """Middleware to add security headers to all responses."""
    response = await handler(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# =============================================================================
# Stats API
# =============================================================================

# Avatar cache: {user_id: (avatar_url, display_name, username, joined_at)}
# Limited to 500 entries to prevent unbounded growth
_avatar_cache: dict[int, tuple[Optional[str], str]] = {}
_avatar_cache_date: Optional[str] = None
_AVATAR_CACHE_MAX_SIZE = 500

# EST timezone for cache refresh
EST_TZ = TIMEZONE_EST


class SyriaAPI:
    """API server for SyriaBot XP Leaderboard."""

    def __init__(self) -> None:
        self._bot: Optional["SyriaBot"] = None
        self._start_time: Optional[datetime] = None
        self.app = web.Application(middlewares=[
            cors_middleware,
            rate_limit_middleware,
            security_headers_middleware,
        ])
        self.runner: Optional[web.AppRunner] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._setup_routes()

    def set_bot(self, bot: "SyriaBot") -> None:
        """Set bot reference."""
        self._bot = bot
        if self._start_time is None:
            self._start_time = datetime.now(DAMASCUS_TZ)

    def _setup_routes(self) -> None:
        """Configure API routes."""
        self.app.router.add_get("/api/syria/leaderboard", self.handle_leaderboard)
        self.app.router.add_get("/api/syria/user/{user_id}", self.handle_user)
        self.app.router.add_get("/api/syria/stats", self.handle_stats)
        self.app.router.add_get("/health", self.handle_health)

    def _format_voice_time(self, mins: int) -> str:
        """Format minutes into human-readable string."""
        if mins >= 60:
            hours = mins // 60
            remaining_mins = mins % 60
            return f"{hours}h {remaining_mins}m"
        return f"{mins}m"

    def _check_cache_refresh(self) -> None:
        """Clear avatar cache if it's a new day in EST or exceeds max size."""
        global _avatar_cache, _avatar_cache_date
        today_est = datetime.now(EST_TZ).strftime("%Y-%m-%d")

        if _avatar_cache_date != today_est:
            _avatar_cache.clear()
            _avatar_cache_date = today_est
        elif len(_avatar_cache) >= _AVATAR_CACHE_MAX_SIZE:
            # Evict oldest half when cache is full
            keys_to_remove = list(_avatar_cache.keys())[:len(_avatar_cache) // 2]
            for key in keys_to_remove:
                del _avatar_cache[key]

    async def _fetch_user_data(self, uid: int) -> tuple[Optional[str], str, Optional[str], Optional[int]]:
        """Fetch avatar, display name, username, and join date for a user."""
        global _avatar_cache

        self._check_cache_refresh()

        # Check cache (now includes joined_at)
        if uid in _avatar_cache:
            cached = _avatar_cache[uid]
            return cached[0], cached[1], cached[2] if len(cached) > 2 else None, cached[3] if len(cached) > 3 else None

        if not self._bot or not self._bot.is_ready():
            return None, str(uid), None, None

        try:
            from src.core.config import config

            # Try to get member from guild for join date
            guild = self._bot.get_guild(config.GUILD_ID)
            member = guild.get_member(uid) if guild else None

            if not member and guild:
                try:
                    member = await asyncio.wait_for(
                        guild.fetch_member(uid),
                        timeout=2.0
                    )
                except Exception:
                    pass

            if member:
                display_name = member.global_name or member.display_name or member.name
                username = member.name
                avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
                joined_at = int(member.joined_at.timestamp()) if member.joined_at else None
                _avatar_cache[uid] = (avatar_url, display_name, username, joined_at)
                return avatar_url, display_name, username, joined_at

            # Fallback to user if not in guild
            user = self._bot.get_user(uid)
            if not user:
                user = await asyncio.wait_for(
                    self._bot.fetch_user(uid),
                    timeout=2.0
                )

            if user:
                display_name = user.global_name or user.display_name or user.name
                username = user.name
                avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
                _avatar_cache[uid] = (avatar_url, display_name, username, None)
                return avatar_url, display_name, username, None
        except (asyncio.TimeoutError, Exception):
            pass

        return None, str(uid), None, None

    async def _enrich_leaderboard(self, leaderboard: list[dict]) -> list[dict]:
        """Add avatar URLs and names to leaderboard entries."""
        if not leaderboard:
            return []

        enriched = []
        for entry in leaderboard:
            user_id = entry["user_id"]
            avatar_url, display_name, username, _ = await self._fetch_user_data(user_id)

            enriched.append({
                "rank": entry["rank"],
                "user_id": str(user_id),
                "display_name": display_name,
                "username": username,
                "avatar": avatar_url,
                "level": entry["level"],
                "xp": entry["xp"],
                "total_messages": entry["total_messages"],
                "voice_minutes": entry["voice_minutes"],
                "voice_formatted": self._format_voice_time(entry["voice_minutes"]),
            })

        return enriched

    async def handle_leaderboard(self, request: web.Request) -> web.Response:
        """GET /api/syria/leaderboard - Return XP leaderboard."""
        client_ip = get_client_ip(request)
        start_time = time.time()

        try:
            # Get query params
            limit = min(int(request.query.get("limit", 50)), 100)
            offset = int(request.query.get("offset", 0))

            # Get leaderboard from database
            raw_leaderboard = db.get_leaderboard(limit=limit, offset=offset)

            # Enrich with Discord data
            leaderboard = await self._enrich_leaderboard(raw_leaderboard)

            # Get total count for pagination
            total_users = db.get_total_ranked_users()

            elapsed_ms = round((time.time() - start_time) * 1000)
            log.tree("Leaderboard API Request", [
                ("Client IP", client_ip),
                ("Limit", str(limit)),
                ("Offset", str(offset)),
                ("Response Time", f"{elapsed_ms}ms"),
            ], emoji="📊")

            return web.json_response({
                "leaderboard": leaderboard,
                "total": total_users,
                "limit": limit,
                "offset": offset,
                "updated_at": datetime.now(DAMASCUS_TZ).isoformat(),
            }, headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=30",
            })

        except Exception as e:
            log.tree("Leaderboard API Error", [
                ("Client IP", client_ip),
                ("Error", str(e)),
            ], emoji="❌")
            return web.json_response(
                {"error": "Internal server error"},
                status=500,
                headers={"Access-Control-Allow-Origin": "*"}
            )

    async def handle_user(self, request: web.Request) -> web.Response:
        """GET /api/syria/user/{user_id} - Return user XP data."""
        client_ip = get_client_ip(request)

        try:
            user_id = int(request.match_info["user_id"])

            # Get user data from database
            from src.core.config import config
            xp_data = db.get_user_xp(user_id, config.GUILD_ID)

            if not xp_data:
                return web.json_response(
                    {"error": "User not found"},
                    status=404,
                    headers={"Access-Control-Allow-Origin": "*"}
                )

            # Get rank
            rank = db.get_user_rank(user_id, config.GUILD_ID)

            # Get Discord info (includes join date)
            avatar_url, display_name, username, joined_at = await self._fetch_user_data(user_id)

            # Calculate progress
            from src.services.xp.utils import xp_progress, xp_for_level
            _, xp_into_level, xp_needed, progress = xp_progress(xp_data["xp"])

            # Calculate activity stats based on server join date
            now = int(time.time())
            days_in_server = max(1, (now - joined_at) // 86400) if joined_at else 1
            xp_per_day = round(xp_data["xp"] / days_in_server, 1) if days_in_server > 0 else 0
            messages_per_day = round(xp_data["total_messages"] / days_in_server, 1) if days_in_server > 0 else 0

            log.tree("User API Request", [
                ("Client IP", client_ip),
                ("User ID", str(user_id)),
            ], emoji="👤")

            return web.json_response({
                "user_id": str(user_id),
                "display_name": display_name,
                "username": username,
                "avatar": avatar_url,
                "rank": rank,
                "level": xp_data["level"],
                "xp": xp_data["xp"],
                "xp_into_level": xp_into_level,
                "xp_for_next": xp_needed,
                "progress": round(progress * 100, 1),
                "total_messages": xp_data["total_messages"],
                "voice_minutes": xp_data["voice_minutes"],
                "voice_formatted": self._format_voice_time(xp_data["voice_minutes"]),
                "joined_at": joined_at,
                "days_in_server": days_in_server,
                "xp_per_day": xp_per_day,
                "messages_per_day": messages_per_day,
                "updated_at": datetime.now(DAMASCUS_TZ).isoformat(),
            }, headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=30",
            })

        except ValueError:
            return web.json_response(
                {"error": "Invalid user ID"},
                status=400,
                headers={"Access-Control-Allow-Origin": "*"}
            )
        except Exception as e:
            log.tree("User API Error", [
                ("Client IP", client_ip),
                ("Error", str(e)),
            ], emoji="❌")
            return web.json_response(
                {"error": "Internal server error"},
                status=500,
                headers={"Access-Control-Allow-Origin": "*"}
            )

    async def handle_stats(self, request: web.Request) -> web.Response:
        """GET /api/syria/stats - Return overall XP stats."""
        client_ip = get_client_ip(request)

        try:
            # Get overall stats from database
            stats = db.get_xp_stats()

            # Get top 3 for quick display
            top_3 = await self._enrich_leaderboard(db.get_leaderboard(limit=3))

            # Get guild info (icon, banner, name)
            guild_icon = None
            guild_banner = None
            guild_name = "Syria"
            member_count = 0

            if self._bot and self._bot.is_ready():
                from src.core.config import config
                guild = self._bot.get_guild(config.GUILD_ID)
                if guild:
                    guild_name = guild.name
                    member_count = guild.member_count or 0
                    if guild.icon:
                        guild_icon = guild.icon.url
                    if guild.banner:
                        guild_banner = guild.banner.url

            log.tree("Stats API Request", [
                ("Client IP", client_ip),
            ], emoji="📈")

            return web.json_response({
                "guild_name": guild_name,
                "guild_icon": guild_icon,
                "guild_banner": guild_banner,
                "member_count": member_count,
                "total_users": stats.get("total_users", 0),
                "total_xp": stats.get("total_xp", 0),
                "total_messages": stats.get("total_messages", 0),
                "total_voice_minutes": stats.get("total_voice_minutes", 0),
                "total_voice_formatted": self._format_voice_time(stats.get("total_voice_minutes", 0)),
                "highest_level": stats.get("highest_level", 0),
                "top_3": top_3,
                "updated_at": datetime.now(DAMASCUS_TZ).isoformat(),
            }, headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=60",
            })

        except Exception as e:
            log.tree("Stats API Error", [
                ("Client IP", client_ip),
                ("Error", str(e)),
            ], emoji="❌")
            return web.json_response(
                {"error": "Internal server error"},
                status=500,
                headers={"Access-Control-Allow-Origin": "*"}
            )

    async def handle_health(self, request: web.Request) -> web.Response:
        """GET /health - Health check endpoint."""
        return web.json_response({"status": "healthy"})

    async def _periodic_cleanup(self) -> None:
        """Periodically cleanup rate limiter stale entries."""
        while True:
            await asyncio.sleep(120)
            await rate_limiter.cleanup()

    async def start(self) -> None:
        """Start the API server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        site = web.TCPSite(self.runner, STATS_API_HOST, STATS_API_PORT)
        await site.start()

        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

        log.tree("Syria API Started", [
            ("Host", STATS_API_HOST),
            ("Port", str(STATS_API_PORT)),
            ("Endpoints", "/api/syria/leaderboard, /api/syria/user/{id}, /api/syria/stats"),
            ("Rate Limit", "60 req/min"),
        ], emoji="🌐")

    async def stop(self) -> None:
        """Stop the API server."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self.runner:
            await self.runner.cleanup()
            log.info("Syria API Stopped")


__all__ = ["SyriaAPI", "STATS_API_PORT"]
