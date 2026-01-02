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

# Avatar cache: {user_id: (avatar_url, display_name, username, joined_at, is_booster)}
# Limited to 500 entries to prevent unbounded growth
_avatar_cache: dict[int, tuple[Optional[str], str, Optional[str], Optional[int], bool]] = {}
_avatar_cache_date: Optional[str] = None
_AVATAR_CACHE_MAX_SIZE = 500

# Response cache for expensive queries
_response_cache: dict[str, tuple[dict, float]] = {}
_STATS_CACHE_TTL = 60  # 60 seconds for stats
_LEADERBOARD_CACHE_TTL = 30  # 30 seconds for leaderboard

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

    async def _fetch_user_data(self, uid: int) -> tuple[Optional[str], str, Optional[str], Optional[int], bool]:
        """Fetch avatar, display name, username, join date, and booster status for a user."""
        global _avatar_cache

        self._check_cache_refresh()

        # Check cache (includes joined_at and is_booster)
        if uid in _avatar_cache:
            cached = _avatar_cache[uid]
            return cached[0], cached[1], cached[2], cached[3], cached[4]

        if not self._bot or not self._bot.is_ready():
            return None, str(uid), None, None, False

        try:
            from src.core.config import config

            # Try to get member from guild for join date and booster status
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
                is_booster = member.premium_since is not None
                _avatar_cache[uid] = (avatar_url, display_name, username, joined_at, is_booster)
                return avatar_url, display_name, username, joined_at, is_booster

            # Fallback to user if not in guild (can't determine booster status)
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
                _avatar_cache[uid] = (avatar_url, display_name, username, None, False)
                return avatar_url, display_name, username, None, False
        except (asyncio.TimeoutError, Exception):
            pass

        return None, str(uid), None, None, False

    async def _enrich_leaderboard(self, leaderboard: list[dict]) -> list[dict]:
        """Add avatar URLs, names, and booster status to leaderboard entries (parallel fetch)."""
        if not leaderboard:
            return []

        # Fetch all user data in parallel for better performance
        user_ids = [entry["user_id"] for entry in leaderboard]
        user_data_tasks = [self._fetch_user_data(uid) for uid in user_ids]
        user_data_results = await asyncio.gather(*user_data_tasks, return_exceptions=True)

        enriched = []
        for entry, user_data in zip(leaderboard, user_data_results):
            # Handle exceptions from parallel fetch
            if isinstance(user_data, Exception):
                avatar_url, display_name, username, is_booster = None, str(entry["user_id"]), None, False
            else:
                avatar_url, display_name, username, _, is_booster = user_data

            enriched.append({
                "rank": entry["rank"],
                "user_id": str(entry["user_id"]),
                "display_name": display_name,
                "username": username,
                "avatar": avatar_url,
                "level": entry["level"],
                "xp": entry["xp"],
                "total_messages": entry["total_messages"],
                "voice_minutes": entry["voice_minutes"],
                "voice_formatted": self._format_voice_time(entry["voice_minutes"]),
                "is_booster": is_booster,
            })

        return enriched

    async def handle_leaderboard(self, request: web.Request) -> web.Response:
        """GET /api/syria/leaderboard - Return XP leaderboard."""
        global _response_cache
        client_ip = get_client_ip(request)
        start_time = time.time()

        try:
            # Get query params
            limit = min(int(request.query.get("limit", 50)), 100)
            offset = int(request.query.get("offset", 0))

            # Check response cache
            cache_key = f"leaderboard:{limit}:{offset}"
            now = time.time()
            if cache_key in _response_cache:
                cached_data, cached_time = _response_cache[cache_key]
                if now - cached_time < _LEADERBOARD_CACHE_TTL:
                    elapsed_ms = round((time.time() - start_time) * 1000)
                    log.tree("Leaderboard API (Cached)", [
                        ("Client IP", client_ip),
                        ("Response Time", f"{elapsed_ms}ms"),
                    ], emoji="⚡")
                    return web.json_response(cached_data, headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "public, max-age=30",
                        "X-Cache": "HIT",
                    })

            # Get leaderboard from database
            raw_leaderboard = db.get_leaderboard(limit=limit, offset=offset)

            # Enrich with Discord data
            leaderboard = await self._enrich_leaderboard(raw_leaderboard)

            # Get total count for pagination
            total_users = db.get_total_ranked_users()

            response_data = {
                "leaderboard": leaderboard,
                "total": total_users,
                "limit": limit,
                "offset": offset,
                "updated_at": datetime.now(DAMASCUS_TZ).isoformat(),
            }

            # Cache the response
            _response_cache[cache_key] = (response_data, now)

            elapsed_ms = round((time.time() - start_time) * 1000)
            log.tree("Leaderboard API Request", [
                ("Client IP", client_ip),
                ("Limit", str(limit)),
                ("Offset", str(offset)),
                ("Response Time", f"{elapsed_ms}ms"),
            ], emoji="📊")

            return web.json_response(response_data, headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=30",
                "X-Cache": "MISS",
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

            # Get Discord info (includes join date and booster status)
            avatar_url, display_name, username, joined_at, is_booster = await self._fetch_user_data(user_id)

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
                ("Booster", "Yes" if is_booster else "No"),
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
                "is_booster": is_booster,
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
        global _response_cache
        client_ip = get_client_ip(request)
        start_time = time.time()

        try:
            # Check response cache
            cache_key = "stats"
            now = time.time()
            if cache_key in _response_cache:
                cached_data, cached_time = _response_cache[cache_key]
                if now - cached_time < _STATS_CACHE_TTL:
                    elapsed_ms = round((time.time() - start_time) * 1000)
                    log.tree("Stats API (Cached)", [
                        ("Client IP", client_ip),
                        ("Response Time", f"{elapsed_ms}ms"),
                    ], emoji="⚡")
                    return web.json_response(cached_data, headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "public, max-age=60",
                        "X-Cache": "HIT",
                    })

            # Get overall stats from database
            stats = db.get_xp_stats()

            # Get top 3 for quick display
            top_3 = await self._enrich_leaderboard(db.get_leaderboard(limit=3))

            # Get guild info (icon, banner, name, booster count)
            guild_icon = None
            guild_banner = None
            guild_name = "Syria"
            member_count = 0
            booster_count = 0

            if self._bot and self._bot.is_ready():
                from src.core.config import config
                guild = self._bot.get_guild(config.GUILD_ID)
                if guild:
                    guild_name = guild.name
                    member_count = guild.member_count or 0
                    booster_count = guild.premium_subscription_count or 0
                    if guild.icon:
                        guild_icon = guild.icon.url
                    if guild.banner:
                        guild_banner = guild.banner.url

            response_data = {
                "guild_name": guild_name,
                "guild_icon": guild_icon,
                "guild_banner": guild_banner,
                "member_count": member_count,
                "booster_count": booster_count,
                "total_users": stats.get("total_users", 0),
                "total_xp": stats.get("total_xp", 0),
                "total_messages": stats.get("total_messages", 0),
                "total_voice_minutes": stats.get("total_voice_minutes", 0),
                "total_voice_formatted": self._format_voice_time(stats.get("total_voice_minutes", 0)),
                "highest_level": stats.get("highest_level", 0),
                "top_3": top_3,
                "updated_at": datetime.now(DAMASCUS_TZ).isoformat(),
            }

            # Cache the response
            _response_cache[cache_key] = (response_data, now)

            elapsed_ms = round((time.time() - start_time) * 1000)
            log.tree("Stats API Request", [
                ("Client IP", client_ip),
                ("Response Time", f"{elapsed_ms}ms"),
            ], emoji="📈")

            return web.json_response(response_data, headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=60",
                "X-Cache": "MISS",
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
        """Periodically cleanup rate limiter and response cache."""
        global _response_cache
        while True:
            await asyncio.sleep(120)
            await rate_limiter.cleanup()

            # Clean expired response cache entries
            now = time.time()
            expired_keys = [
                k for k, (_, ts) in _response_cache.items()
                if now - ts > max(_STATS_CACHE_TTL, _LEADERBOARD_CACHE_TTL) * 2
            ]
            for k in expired_keys:
                del _response_cache[k]

    async def _midnight_booster_refresh(self) -> None:
        """Refresh booster status for all cached users at midnight EST."""
        global _avatar_cache, _response_cache

        while True:
            try:
                # Calculate seconds until next midnight EST
                now_est = datetime.now(EST_TZ)
                tomorrow = now_est.replace(hour=0, minute=0, second=0, microsecond=0)
                if now_est.hour >= 0:
                    tomorrow += __import__('datetime').timedelta(days=1)
                seconds_until_midnight = (tomorrow - now_est).total_seconds()

                log.tree("Midnight Booster Refresh Scheduled", [
                    ("Next Run", tomorrow.strftime("%Y-%m-%d %H:%M:%S EST")),
                    ("Wait Time", f"{int(seconds_until_midnight // 3600)}h {int((seconds_until_midnight % 3600) // 60)}m"),
                ], emoji="⏰")

                await asyncio.sleep(seconds_until_midnight)

                # Run the refresh
                await self._refresh_all_booster_status()

            except asyncio.CancelledError:
                log.tree("Midnight Booster Refresh", [
                    ("Status", "Task cancelled"),
                ], emoji="⏹️")
                break
            except Exception as e:
                log.tree("Midnight Refresh Scheduler Error", [
                    ("Error", str(e)[:100]),
                ], emoji="❌")
                # Wait an hour before retrying on error
                await asyncio.sleep(3600)

    async def _refresh_all_booster_status(self) -> None:
        """Refresh booster status for all cached users. Non-blocking with staggered checks."""
        global _avatar_cache, _response_cache

        if not self._bot or not self._bot.is_ready():
            log.tree("Booster Refresh Skipped", [
                ("Reason", "Bot not ready"),
            ], emoji="⚠️")
            return

        from src.core.config import config
        guild = self._bot.get_guild(config.GUILD_ID)
        if not guild:
            log.tree("Booster Refresh Skipped", [
                ("Reason", "Guild not found"),
            ], emoji="⚠️")
            return

        start_time = time.time()
        cached_user_ids = list(_avatar_cache.keys())
        total_users = len(cached_user_ids)

        if total_users == 0:
            log.tree("Booster Refresh Skipped", [
                ("Reason", "No users in cache"),
            ], emoji="ℹ️")
            return

        log.tree("Midnight Booster Refresh Started", [
            ("Users to Check", str(total_users)),
            ("Guild", guild.name),
        ], emoji="🔄")

        updated = 0
        errors = 0
        unchanged = 0

        for i, user_id in enumerate(cached_user_ids):
            try:
                # Get member from guild
                member = guild.get_member(user_id)
                if not member:
                    try:
                        member = await guild.fetch_member(user_id)
                    except Exception:
                        # User left the server, remove from cache
                        if user_id in _avatar_cache:
                            del _avatar_cache[user_id]
                        continue

                # Check current booster status
                current_is_booster = member.premium_since is not None

                # Get cached status
                if user_id in _avatar_cache:
                    cached_data = _avatar_cache[user_id]
                    cached_is_booster = cached_data[4] if len(cached_data) > 4 else False

                    if current_is_booster != cached_is_booster:
                        # Status changed - update cache
                        display_name = member.global_name or member.display_name or member.name
                        username = member.name
                        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
                        joined_at = int(member.joined_at.timestamp()) if member.joined_at else None

                        _avatar_cache[user_id] = (avatar_url, display_name, username, joined_at, current_is_booster)
                        updated += 1

                        log.tree("Booster Status Updated", [
                            ("User", f"{member.name} ({user_id})"),
                            ("Old Status", "Booster" if cached_is_booster else "Non-booster"),
                            ("New Status", "Booster" if current_is_booster else "Non-booster"),
                        ], emoji="💎" if current_is_booster else "💔")
                    else:
                        unchanged += 1

                # Stagger checks to avoid blocking (10ms between each)
                if (i + 1) % 50 == 0:
                    await asyncio.sleep(0.5)  # 500ms pause every 50 users
                else:
                    await asyncio.sleep(0.01)  # 10ms between users

            except Exception as e:
                errors += 1
                if errors <= 3:  # Only log first 3 errors
                    log.tree("Booster Check Error", [
                        ("User ID", str(user_id)),
                        ("Error", str(e)[:50]),
                    ], emoji="⚠️")

        # Clear response cache if any updates occurred
        if updated > 0:
            _response_cache.clear()

        elapsed = round(time.time() - start_time, 2)

        log.tree("Midnight Booster Refresh Complete", [
            ("Total Checked", str(total_users)),
            ("Updated", str(updated)),
            ("Unchanged", str(unchanged)),
            ("Errors", str(errors)),
            ("Duration", f"{elapsed}s"),
        ], emoji="✅")

    async def start(self) -> None:
        """Start the API server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        site = web.TCPSite(self.runner, STATS_API_HOST, STATS_API_PORT)
        await site.start()

        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self._midnight_task = asyncio.create_task(self._midnight_booster_refresh())

        log.tree("Syria API Started", [
            ("Host", STATS_API_HOST),
            ("Port", str(STATS_API_PORT)),
            ("Endpoints", "/api/syria/leaderboard, /api/syria/user/{id}, /api/syria/stats"),
            ("Rate Limit", "60 req/min"),
            ("Midnight Refresh", "Enabled"),
        ], emoji="🌐")

    async def stop(self) -> None:
        """Stop the API server."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, '_midnight_task') and self._midnight_task:
            self._midnight_task.cancel()
            try:
                await self._midnight_task
            except asyncio.CancelledError:
                pass

        if self.runner:
            await self.runner.cleanup()
            log.tree("Syria API Stopped", [
                ("Status", "Shutdown complete"),
            ], emoji="🛑")


__all__ = ["SyriaAPI", "STATS_API_PORT"]
