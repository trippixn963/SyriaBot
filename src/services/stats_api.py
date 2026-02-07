"""
SyriaBot - Stats API
====================

HTTP API server for SyriaBot XP Leaderboard Dashboard.

Exposes XP stats, leaderboard, and user data.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import hmac
import time
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta
from aiohttp import web
from typing import TYPE_CHECKING, Optional

from src.core.logger import logger
from src.core.config import config
from src.core.constants import (
    STATS_API_PORT,
    STATS_API_HOST,
    TIMEZONE_DAMASCUS,
    TIMEZONE_EST,
)
from src.services.database import db
from src.services.xp.utils import level_from_xp

if TYPE_CHECKING:
    from src.bot import SyriaBot

# Aliases for backwards compatibility
DAMASCUS_TZ = TIMEZONE_DAMASCUS


# =============================================================================
# Rate Limiting
# =============================================================================

class RateLimiter:
    """Simple in-memory rate limiter using sliding window with LRU eviction."""

    # Max number of unique IPs to track (prevents unbounded memory growth)
    MAX_TRACKED_IPS = 10000

    def __init__(self, requests_per_minute: int = 60, burst_limit: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        # Use OrderedDict for O(1) LRU eviction - most recent at end
        self._requests: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_ip: str) -> tuple[bool, Optional[int]]:
        """Check if request is allowed for this IP."""
        async with self._lock:
            now = time.time()
            window_start = now - 60

            # Get or create request list for this IP
            if client_ip in self._requests:
                # Move to end (most recently used)
                self._requests.move_to_end(client_ip)
                # Clean old requests
                self._requests[client_ip] = [
                    ts for ts in self._requests[client_ip]
                    if ts > window_start
                ]
            else:
                self._requests[client_ip] = []

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

            # Evict oldest IPs (from front of OrderedDict) if we exceed limit
            # This is O(1) per removal since OrderedDict maintains insertion order
            if len(self._requests) > self.MAX_TRACKED_IPS:
                to_remove = len(self._requests) - (self.MAX_TRACKED_IPS * 9 // 10)
                removed = 0
                for _ in range(to_remove):
                    if self._requests:
                        self._requests.popitem(last=False)  # Remove oldest (front)
                        removed += 1
                if removed > 0:
                    logger.tree("Rate Limiter IP Eviction", [
                        ("Removed", str(removed)),
                        ("Remaining", str(len(self._requests))),
                    ], emoji="🧹")

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


# Global rate limiter (disabled for dashboard - own infrastructure)
rate_limiter = RateLimiter(requests_per_minute=10000, burst_limit=1000)


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

    # Log when we can't determine IP (rate limiting may not work properly)
    logger.tree("API IP Detection Failed", [
        ("Path", request.path),
        ("Fallback", "unknown"),
    ], emoji="⚠️")
    return "unknown"


@web.middleware
async def rate_limit_middleware(request: web.Request, handler) -> web.Response:
    """Middleware to enforce rate limiting on all requests."""
    if request.path == "/health":
        return await handler(request)

    client_ip = get_client_ip(request)
    allowed, retry_after = await rate_limiter.is_allowed(client_ip)

    if not allowed:
        logger.tree("Rate Limit Exceeded", [
            ("IP", client_ip),
            ("Path", request.path),
            ("Retry-After", f"{retry_after}s"),
        ], emoji="⚠️")
        # CORS headers will be added by cors_middleware wrapper
        return web.json_response(
            {"error": "Rate limit exceeded", "retry_after": retry_after},
            status=429,
            headers={"Retry-After": str(retry_after)}
        )

    return await handler(request)


# Allowed CORS origins for the API
ALLOWED_ORIGINS = frozenset([
    "https://trippixn.com",
    "https://www.trippixn.com",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
])


def _get_cors_origin(request: web.Request) -> str:
    """Get CORS origin header - return specific origin if allowed, empty otherwise."""
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        return origin
    # Allow same-origin requests (no Origin header)
    return ""


@web.middleware
async def cors_middleware(request: web.Request, handler) -> web.Response:
    """Middleware to add CORS headers to all responses."""
    origin = _get_cors_origin(request)

    # Handle preflight OPTIONS requests
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-API-Key",
            "Access-Control-Max-Age": "86400",
        }
        if origin:
            headers["Access-Control-Allow-Origin"] = origin
        return web.Response(status=204, headers=headers)

    response = await handler(request)
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
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
# Uses OrderedDict for LRU eviction, limited to 500 entries
_avatar_cache: OrderedDict[int, tuple[Optional[str], str, Optional[str], Optional[int], bool]] = OrderedDict()
_avatar_cache_date: Optional[str] = None
_avatar_cache_lock: asyncio.Lock = asyncio.Lock()
_AVATAR_CACHE_MAX_SIZE = 500

# Response cache for expensive queries
_response_cache: dict[str, tuple[dict, float]] = {}
_response_cache_lock: asyncio.Lock = asyncio.Lock()
_RESPONSE_CACHE_MAX_SIZE = 200  # Limit cache entries to prevent memory abuse
_STATS_CACHE_TTL = 60  # 60 seconds for stats
_LEADERBOARD_CACHE_TTL = 30  # 30 seconds for leaderboard

# EST timezone for cache refresh
EST_TZ = TIMEZONE_EST


class SyriaAPI:
    """API server for SyriaBot XP Leaderboard."""

    def __init__(self, bot: "SyriaBot") -> None:
        self._bot = bot
        self._start_time: Optional[datetime] = None
        self.app = web.Application(middlewares=[
            cors_middleware,
            rate_limit_middleware,
            security_headers_middleware,
        ])
        self.runner: Optional[web.AppRunner] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Configure API routes."""
        # Read-only endpoints (public)
        self.app.router.add_get("/api/syria/leaderboard", self.handle_leaderboard)
        self.app.router.add_get("/api/syria/user/{user_id}", self.handle_user)
        self.app.router.add_get("/api/syria/stats", self.handle_stats)
        self.app.router.add_get("/api/syria/channels", self.handle_channels)
        self.app.router.add_get("/health", self.handle_health)

        # XP modification endpoints (require API key)
        self.app.router.add_post("/api/syria/xp/grant", self.handle_xp_grant)
        self.app.router.add_post("/api/syria/xp/set", self.handle_xp_set)

    def _verify_api_key(self, request: web.Request) -> bool:
        """Verify the API key from request header using constant-time comparison."""
        if not config.XP_API_KEY:
            return False  # API key not configured

        api_key = request.headers.get("X-API-Key", "")
        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(api_key, config.XP_API_KEY)

    def _format_voice_time(self, mins: int) -> str:
        """Format minutes into human-readable string."""
        if mins >= 60:
            hours = mins // 60
            remaining_mins = mins % 60
            return f"{hours}h {remaining_mins}m"
        return f"{mins}m"

    async def _check_cache_refresh(self) -> None:
        """Clear avatar cache if it's a new day in EST or exceeds max size."""
        global _avatar_cache, _avatar_cache_date
        today_est = datetime.now(EST_TZ).strftime("%Y-%m-%d")

        async with _avatar_cache_lock:
            if _avatar_cache_date != today_est:
                _avatar_cache.clear()
                _avatar_cache_date = today_est
            elif len(_avatar_cache) >= _AVATAR_CACHE_MAX_SIZE:
                # LRU eviction: remove oldest 10% (50 entries) instead of 50%
                evict_count = max(1, _AVATAR_CACHE_MAX_SIZE // 10)
                for _ in range(evict_count):
                    if _avatar_cache:
                        _avatar_cache.popitem(last=False)  # Remove oldest

    async def _fetch_user_data(self, uid: int) -> tuple[Optional[str], str, Optional[str], Optional[int], bool]:
        """Fetch avatar, display name, username, join date, and booster status for a user."""
        global _avatar_cache

        await self._check_cache_refresh()

        # Check cache (includes joined_at and is_booster)
        async with _avatar_cache_lock:
            if uid in _avatar_cache:
                # Move to end for LRU (most recently used)
                _avatar_cache.move_to_end(uid)
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
                # Prefer guild avatar (server-specific), fall back to global avatar
                if member.guild_avatar:
                    avatar_url = member.guild_avatar.url
                elif member.avatar:
                    avatar_url = member.avatar.url
                else:
                    avatar_url = member.default_avatar.url
                joined_at = int(member.joined_at.timestamp()) if member.joined_at else None
                is_booster = member.premium_since is not None
                async with _avatar_cache_lock:
                    _avatar_cache[uid] = (avatar_url, display_name, username, joined_at, is_booster)
                    # Enforce cache size limit after adding
                    while len(_avatar_cache) > _AVATAR_CACHE_MAX_SIZE:
                        _avatar_cache.popitem(last=False)
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
                async with _avatar_cache_lock:
                    _avatar_cache[uid] = (avatar_url, display_name, username, None, False)
                    # Enforce cache size limit after adding
                    while len(_avatar_cache) > _AVATAR_CACHE_MAX_SIZE:
                        _avatar_cache.popitem(last=False)
                return avatar_url, display_name, username, None, False
        except asyncio.TimeoutError:
            # Timeout is expected for users not in cache - don't log
            pass
        except Exception as e:
            # Log unexpected errors (rate limits, API errors, etc.)
            logger.tree("User Fetch Error", [
                ("ID", str(uid)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        return None, str(uid), None, None, False

    def _format_last_seen(self, last_active_at: int) -> str:
        """Format last_active_at timestamp as human-readable 'time ago'."""
        if not last_active_at or last_active_at <= 0:
            return "Unknown"

        now = int(time.time())
        seconds_ago = now - last_active_at

        if seconds_ago < 60:
            return "Just now"
        elif seconds_ago < 3600:
            mins = seconds_ago // 60
            return f"{mins}m ago"
        elif seconds_ago < 86400:
            hours = seconds_ago // 3600
            return f"{hours}h ago"
        else:
            days = seconds_ago // 86400
            return f"{days}d ago"

    async def _enrich_leaderboard(
        self,
        leaderboard: list[dict],
        include_xp_gained: bool = False,
        previous_ranks: dict[int, int] = None
    ) -> list[dict]:
        """Add avatar URLs, names, booster status, and rank changes to leaderboard entries."""
        if not leaderboard:
            return []

        # Use semaphore to limit concurrent Discord API calls (prevent rate limit flood)
        MAX_CONCURRENT_FETCHES = 10
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)

        async def fetch_with_limit(uid: int):
            async with semaphore:
                return await self._fetch_user_data(uid)

        # Fetch all user data with limited concurrency
        user_ids = [entry["user_id"] for entry in leaderboard]
        user_data_tasks = [fetch_with_limit(uid) for uid in user_ids]
        user_data_results = await asyncio.gather(*user_data_tasks, return_exceptions=True)

        enriched = []
        for entry, user_data in zip(leaderboard, user_data_results):
            # Handle exceptions from parallel fetch
            if isinstance(user_data, Exception):
                avatar_url, display_name, username, is_booster = None, str(entry["user_id"]), None, False
            else:
                avatar_url, display_name, username, _, is_booster = user_data

            # Get activity data
            last_active_at = entry.get("last_active_at", 0) or 0
            streak_days = entry.get("streak_days", 0) or 0

            # Calculate rank change (positive = moved up, negative = moved down)
            rank_change = None
            current_rank = entry["rank"]
            user_id = entry["user_id"]
            if previous_ranks and user_id in previous_ranks:
                previous_rank = previous_ranks[user_id]
                # If previous rank was 5 and current is 3, change is +2 (moved up)
                rank_change = previous_rank - current_rank

            enriched_entry = {
                "rank": current_rank,
                "rank_change": rank_change,
                "user_id": str(user_id),
                "display_name": display_name,
                "username": username,
                "avatar": avatar_url,
                "level": entry["level"],
                "xp": entry["xp"],
                "total_messages": entry["total_messages"],
                "voice_minutes": entry["voice_minutes"],
                "voice_formatted": self._format_voice_time(entry["voice_minutes"]),
                "is_booster": is_booster,
                "last_active_at": last_active_at if last_active_at > 0 else None,
                "last_seen": self._format_last_seen(last_active_at),
                "streak_days": streak_days,
            }

            # Include XP gained during period (for period leaderboards)
            if include_xp_gained and "xp_gained" in entry:
                enriched_entry["xp_gained"] = entry["xp_gained"]

            enriched.append(enriched_entry)

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

            # Get period filter (all, month, week, today)
            period = request.query.get("period", "all")
            if period not in ("all", "month", "week", "today"):
                period = "all"

            # Check response cache (include period in key)
            cache_key = f"leaderboard:{limit}:{offset}:{period}"
            now = time.time()
            if cache_key in _response_cache:
                cached_data, cached_time = _response_cache[cache_key]
                if now - cached_time < _LEADERBOARD_CACHE_TTL:
                    elapsed_ms = round((time.time() - start_time) * 1000)
                    logger.tree("Leaderboard API (Cached)", [
                        ("Client IP", client_ip),
                        ("Period", period),
                        ("Response Time", f"{elapsed_ms}ms"),
                    ], emoji="⚡")
                    return web.json_response(cached_data, headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "public, max-age=30",
                        "X-Cache": "HIT",
                    })

            # Get leaderboard from database with period filter
            # For period queries (today/week/month), use period leaderboard which calculates XP gained
            if period != "all":
                raw_leaderboard = db.get_period_leaderboard(limit=limit, offset=offset, period=period)
                total_users = db.get_total_period_users(period=period)
            else:
                raw_leaderboard = db.get_leaderboard(limit=limit, offset=offset, period="all")
                total_users = db.get_total_ranked_users(period="all")

            # Get previous ranks for rank change calculation (only for users on this page)
            user_ids = [entry["user_id"] for entry in raw_leaderboard]
            previous_ranks = db.get_previous_ranks(user_ids=user_ids) if user_ids else {}

            # Enrich with Discord data and rank changes
            leaderboard = await self._enrich_leaderboard(
                raw_leaderboard,
                include_xp_gained=(period != "all"),
                previous_ranks=previous_ranks
            )

            response_data = {
                "leaderboard": leaderboard,
                "total": total_users,
                "limit": limit,
                "offset": offset,
                "period": period,
                "updated_at": datetime.now(DAMASCUS_TZ).isoformat(),
            }

            # Cache the response with size limit enforcement
            _response_cache[cache_key] = (response_data, now)
            # Evict oldest entries if cache exceeds limit
            while len(_response_cache) > _RESPONSE_CACHE_MAX_SIZE:
                oldest_key = min(_response_cache, key=lambda k: _response_cache[k][1])
                del _response_cache[oldest_key]

            elapsed_ms = round((time.time() - start_time) * 1000)
            logger.tree("Leaderboard API Request", [
                ("Client IP", client_ip),
                ("Limit", str(limit)),
                ("Offset", str(offset)),
                ("Period", period),
                ("Response Time", f"{elapsed_ms}ms"),
            ], emoji="📊")

            return web.json_response(response_data, headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=30",
                "X-Cache": "MISS",
            })

        except Exception as e:
            logger.error_tree("Leaderboard API Error", e, [
                ("Client IP", client_ip),
                ("Limit", str(request.query.get("limit", "50"))),
                ("Offset", str(request.query.get("offset", "0"))),
                ("Period", str(request.query.get("period", "all"))),
            ])
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

            # Get previous rank for rank change calculation (only for this user)
            previous_ranks = db.get_previous_ranks(user_ids=[user_id])
            rank_change = None
            if user_id in previous_ranks:
                rank_change = previous_ranks[user_id] - rank

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

            # Activity tracking
            last_active_at = xp_data.get("last_active_at", 0) or 0
            streak_days = xp_data.get("streak_days", 0) or 0
            last_seen = self._format_last_seen(last_active_at)

            # Extended stats (already tracked in database)
            commands_used = xp_data.get("commands_used", 0) or 0
            reactions_given = xp_data.get("reactions_given", 0) or 0
            images_shared = xp_data.get("images_shared", 0) or 0
            total_voice_sessions = xp_data.get("total_voice_sessions", 0) or 0
            longest_voice_session = xp_data.get("longest_voice_session", 0) or 0
            first_message_at = xp_data.get("first_message_at", 0) or 0
            mentions_received = xp_data.get("mentions_received", 0) or 0

            # Get peak activity hour
            peak_hour, peak_hour_count = db.get_peak_activity_hour(user_id, config.GUILD_ID)

            # Get invite count
            invites_count = db.get_invite_count(user_id, config.GUILD_ID)

            # Get top channel activity for this user
            channel_activity = db.get_user_channel_activity(user_id, config.GUILD_ID, limit=10)
            channels = [
                {
                    "channel_id": str(ch.get("channel_id")),
                    "channel_name": ch.get("channel_name", "Unknown"),
                    "message_count": ch.get("message_count", 0),
                }
                for ch in channel_activity
            ]

            logger.tree("User API Request", [
                ("Client IP", client_ip),
                ("ID", str(user_id)),
                ("Booster", "Yes" if is_booster else "No"),
                ("Channels", str(len(channels))),
            ], emoji="👤")

            return web.json_response({
                "user_id": str(user_id),
                "display_name": display_name,
                "username": username,
                "avatar": avatar_url,
                "rank": rank,
                "rank_change": rank_change,
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
                "last_active_at": last_active_at if last_active_at > 0 else None,
                "last_seen": last_seen,
                "streak_days": streak_days,
                # New extended stats
                "commands_used": commands_used,
                "reactions_given": reactions_given,
                "images_shared": images_shared,
                "total_voice_sessions": total_voice_sessions,
                "longest_voice_session": longest_voice_session,
                "longest_voice_formatted": self._format_voice_time(longest_voice_session),
                "first_message_at": first_message_at if first_message_at > 0 else None,
                "peak_hour": peak_hour if peak_hour >= 0 else None,
                "peak_hour_count": peak_hour_count,
                "invites_count": invites_count,
                "mentions_received": mentions_received,
                "channels": channels,
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
            logger.error_tree("User API Error", e, [
                ("Client IP", client_ip),
                ("ID", request.match_info.get("user_id", "unknown")),
            ])
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
                    logger.tree("Stats API (Cached)", [
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

            # Get today's daily stats
            from datetime import timezone
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            daily_stats = db.get_daily_stats(config.GUILD_ID, days=7)

            # Find today's stats
            today_stats = next(
                (d for d in daily_stats if d.get("date") == today_str),
                {"unique_users": 0, "new_members": 0, "voice_peak_users": 0}
            )

            # Format daily stats history
            daily_stats_history = [
                {
                    "date": d.get("date"),
                    "unique_users": d.get("unique_users", 0),
                    "total_messages": d.get("total_messages", 0),
                    "voice_peak_users": d.get("voice_peak_users", 0),
                    "new_members": d.get("new_members", 0),
                }
                for d in daily_stats
            ]

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
                # New daily stats fields
                "daily_active_users": today_stats.get("unique_users", 0),
                "new_members_today": today_stats.get("new_members", 0),
                "voice_peak_today": today_stats.get("voice_peak_users", 0),
                "daily_stats_history": daily_stats_history,
                "updated_at": datetime.now(DAMASCUS_TZ).isoformat(),
            }

            # Cache the response with size limit enforcement
            _response_cache[cache_key] = (response_data, now)
            # Evict oldest entries if cache exceeds limit
            while len(_response_cache) > _RESPONSE_CACHE_MAX_SIZE:
                oldest_key = min(_response_cache, key=lambda k: _response_cache[k][1])
                del _response_cache[oldest_key]

            elapsed_ms = round((time.time() - start_time) * 1000)
            logger.tree("Stats API Request", [
                ("Client IP", client_ip),
                ("Response Time", f"{elapsed_ms}ms"),
            ], emoji="📈")

            return web.json_response(response_data, headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=60",
                "X-Cache": "MISS",
            })

        except Exception as e:
            logger.error_tree("Stats API Error", e, [
                ("Client IP", client_ip),
            ])
            return web.json_response(
                {"error": "Internal server error"},
                status=500,
                headers={"Access-Control-Allow-Origin": "*"}
            )

    async def handle_channels(self, request: web.Request) -> web.Response:
        """GET /api/syria/channels - Return per-channel message counts."""
        global _response_cache
        client_ip = get_client_ip(request)
        start_time = time.time()

        try:
            # Check response cache
            cache_key = "channels"
            now = time.time()
            if cache_key in _response_cache:
                cached_data, cached_time = _response_cache[cache_key]
                if now - cached_time < _STATS_CACHE_TTL:
                    elapsed_ms = round((time.time() - start_time) * 1000)
                    logger.tree("Channels API (Cached)", [
                        ("Client IP", client_ip),
                        ("Response Time", f"{elapsed_ms}ms"),
                    ], emoji="⚡")
                    return web.json_response(cached_data, headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "public, max-age=60",
                        "X-Cache": "HIT",
                    })

            # Get channel stats from database
            channel_stats = db.get_channel_stats(config.GUILD_ID, limit=100)

            # Format response
            channels = [
                {
                    "channel_id": str(ch.get("channel_id")),
                    "channel_name": ch.get("channel_name", "Unknown"),
                    "total_messages": ch.get("total_messages", 0),
                }
                for ch in channel_stats
            ]

            response_data = {
                "channels": channels,
                "updated_at": datetime.now(DAMASCUS_TZ).isoformat(),
            }

            # Cache the response
            _response_cache[cache_key] = (response_data, now)
            while len(_response_cache) > _RESPONSE_CACHE_MAX_SIZE:
                oldest_key = min(_response_cache, key=lambda k: _response_cache[k][1])
                del _response_cache[oldest_key]

            elapsed_ms = round((time.time() - start_time) * 1000)
            logger.tree("Channels API Request", [
                ("Client IP", client_ip),
                ("Channels", str(len(channels))),
                ("Response Time", f"{elapsed_ms}ms"),
            ], emoji="📺")

            return web.json_response(response_data, headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=60",
                "X-Cache": "MISS",
            })

        except Exception as e:
            logger.error_tree("Channels API Error", e, [
                ("Client IP", client_ip),
            ])
            return web.json_response(
                {"error": "Internal server error"},
                status=500,
                headers={"Access-Control-Allow-Origin": "*"}
            )

    async def handle_health(self, request: web.Request) -> web.Response:
        """GET /health - Health check endpoint with full status."""
        now = datetime.now(EST_TZ)
        start = self._start_time or now
        uptime_seconds = (now - start).total_seconds()

        # Format uptime as human-readable
        hours, remainder = divmod(int(uptime_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        # Get bot status
        is_ready = self._bot.is_ready()
        latency_ms = round(self._bot.latency * 1000) if is_ready else None

        status = {
            "status": "healthy" if is_ready else "starting",
            "bot": "SyriaBot",
            "run_id": getattr(logger, "run_id", None),
            "uptime": uptime_str,
            "uptime_seconds": int(uptime_seconds),
            "started_at": start.isoformat(),
            "timestamp": now.isoformat(),
            "timezone": "America/New_York (EST)",
            "discord": {
                "connected": is_ready,
                "latency_ms": latency_ms,
                "guilds": len(self._bot.guilds) if is_ready else 0,
            },
        }

        return web.json_response(status)

    # =========================================================================
    # XP Modification Endpoints (require API key)
    # =========================================================================

    async def handle_xp_grant(self, request: web.Request) -> web.Response:
        """
        POST /api/syria/xp/grant - Grant XP to a user.

        Request body:
        {
            "user_id": 123456789,
            "amount": 100,
            "reason": "minigame win"  // optional, for logging
        }

        Headers:
        X-API-Key: your-api-key
        """
        client_ip = get_client_ip(request)

        # Verify API key
        if not self._verify_api_key(request):
            logger.tree("XP Grant Unauthorized", [
                ("Client IP", client_ip),
                ("Reason", "Invalid or missing API key"),
            ], emoji="🔒")
            return web.json_response(
                {"error": "Unauthorized", "message": "Invalid or missing API key"},
                status=401,
                headers={"Access-Control-Allow-Origin": "*"}
            )

        try:
            data = await request.json()
        except Exception:
            logger.tree("XP Grant Bad Request", [
                ("Client IP", client_ip),
                ("Error", "Invalid JSON body"),
            ], emoji="⚠️")
            return web.json_response(
                {"error": "Bad Request", "message": "Invalid JSON body"},
                status=400,
                headers={"Access-Control-Allow-Origin": "*"}
            )

        user_id = data.get("user_id")
        amount = data.get("amount")
        reason = data.get("reason", "API grant")

        # Validate required fields
        if not user_id or not isinstance(user_id, int):
            logger.tree("XP Grant Bad Request", [
                ("Client IP", client_ip),
                ("Error", "user_id (int) is required"),
                ("Received", str(user_id)[:50]),
            ], emoji="⚠️")
            return web.json_response(
                {"error": "Bad Request", "message": "user_id (int) is required"},
                status=400,
                headers={"Access-Control-Allow-Origin": "*"}
            )

        if amount is None or not isinstance(amount, int):
            logger.tree("XP Grant Bad Request", [
                ("Client IP", client_ip),
                ("ID", str(user_id)),
                ("Error", "amount (int) is required"),
                ("Received", str(amount)[:50]),
            ], emoji="⚠️")
            return web.json_response(
                {"error": "Bad Request", "message": "amount (int) is required"},
                status=400,
                headers={"Access-Control-Allow-Origin": "*"}
            )

        if amount <= 0 or amount > 100000:
            logger.tree("XP Grant Bad Request", [
                ("Client IP", client_ip),
                ("ID", str(user_id)),
                ("Error", "amount out of range"),
                ("Amount", str(amount)),
            ], emoji="⚠️")
            return web.json_response(
                {"error": "Bad Request", "message": "amount must be between 1 and 100000"},
                status=400,
                headers={"Access-Control-Allow-Origin": "*"}
            )

        try:
            # Get current XP data (non-blocking)
            guild_id = config.GUILD_ID
            user_data = await asyncio.to_thread(db.get_user_xp, user_id, guild_id)

            if not user_data:
                # Create new user entry
                user_data = await asyncio.to_thread(db.ensure_user_xp, user_id, guild_id)

            current_xp = user_data.get("xp", 0)
            current_level = user_data.get("level", 0)
            new_xp = current_xp + amount
            new_level = level_from_xp(new_xp)

            # Update XP in database (non-blocking)
            await asyncio.to_thread(db.add_xp, user_id, guild_id, amount)

            logger.tree("XP Granted via API", [
                ("ID", str(user_id)),
                ("Amount", f"+{amount}"),
                ("New XP", str(new_xp)),
                ("Level", f"{current_level} → {new_level}" if new_level != current_level else str(new_level)),
                ("Reason", reason[:50]),
                ("Client IP", client_ip),
            ], emoji="⬆️")

            # Clear response cache to reflect new data
            global _response_cache
            _response_cache.clear()

            return web.json_response({
                "success": True,
                "user_id": user_id,
                "xp_added": amount,
                "new_xp": new_xp,
                "old_level": current_level,
                "new_level": new_level,
                "leveled_up": new_level > current_level,
            }, headers={"Access-Control-Allow-Origin": "*"})

        except Exception as e:
            logger.error_tree("XP Grant API Error", e, [
                ("ID", str(user_id)),
                ("Amount", str(amount)),
                ("Client IP", client_ip),
            ])
            # Don't expose internal error details to clients (may contain secrets)
            return web.json_response(
                {"error": "Internal server error"},
                status=500,
                headers={"Access-Control-Allow-Origin": "*"}
            )

    async def handle_xp_set(self, request: web.Request) -> web.Response:
        """
        POST /api/syria/xp/set - Set XP for a user (overwrites).

        Request body:
        {
            "user_id": 123456789,
            "xp": 5000,
            "reason": "admin adjustment"  // optional
        }

        Headers:
        X-API-Key: your-api-key
        """
        client_ip = get_client_ip(request)

        # Verify API key
        if not self._verify_api_key(request):
            logger.tree("XP Set Unauthorized", [
                ("Client IP", client_ip),
                ("Reason", "Invalid or missing API key"),
            ], emoji="🔒")
            return web.json_response(
                {"error": "Unauthorized", "message": "Invalid or missing API key"},
                status=401,
                headers={"Access-Control-Allow-Origin": "*"}
            )

        try:
            data = await request.json()
        except Exception:
            logger.tree("XP Set Bad Request", [
                ("Client IP", client_ip),
                ("Error", "Invalid JSON body"),
            ], emoji="⚠️")
            return web.json_response(
                {"error": "Bad Request", "message": "Invalid JSON body"},
                status=400,
                headers={"Access-Control-Allow-Origin": "*"}
            )

        user_id = data.get("user_id")
        new_xp = data.get("xp")
        reason = data.get("reason", "API set")

        # Validate required fields
        if not user_id or not isinstance(user_id, int):
            logger.tree("XP Set Bad Request", [
                ("Client IP", client_ip),
                ("Error", "user_id (int) is required"),
                ("Received", str(user_id)[:50]),
            ], emoji="⚠️")
            return web.json_response(
                {"error": "Bad Request", "message": "user_id (int) is required"},
                status=400,
                headers={"Access-Control-Allow-Origin": "*"}
            )

        if new_xp is None or not isinstance(new_xp, int):
            logger.tree("XP Set Bad Request", [
                ("Client IP", client_ip),
                ("ID", str(user_id)),
                ("Error", "xp (int) is required"),
                ("Received", str(new_xp)[:50]),
            ], emoji="⚠️")
            return web.json_response(
                {"error": "Bad Request", "message": "xp (int) is required"},
                status=400,
                headers={"Access-Control-Allow-Origin": "*"}
            )

        if new_xp < 0 or new_xp > 10000000:
            logger.tree("XP Set Bad Request", [
                ("Client IP", client_ip),
                ("ID", str(user_id)),
                ("Error", "xp out of range"),
                ("XP", str(new_xp)),
            ], emoji="⚠️")
            return web.json_response(
                {"error": "Bad Request", "message": "xp must be between 0 and 10000000"},
                status=400,
                headers={"Access-Control-Allow-Origin": "*"}
            )

        try:
            guild_id = config.GUILD_ID
            user_data = await asyncio.to_thread(db.get_user_xp, user_id, guild_id)

            old_xp = 0
            old_level = 0
            if user_data:
                old_xp = user_data.get("xp", 0)
                old_level = user_data.get("level", 0)

            new_level = level_from_xp(new_xp)

            # Set XP in database (non-blocking)
            await asyncio.to_thread(db.set_xp, user_id, guild_id, new_xp, new_level)

            logger.tree("XP Set via API", [
                ("ID", str(user_id)),
                ("XP", f"{old_xp} → {new_xp}"),
                ("Level", f"{old_level} → {new_level}"),
                ("Reason", reason[:50]),
                ("Client IP", client_ip),
            ], emoji="✏️")

            # Clear response cache
            global _response_cache
            _response_cache.clear()

            return web.json_response({
                "success": True,
                "user_id": user_id,
                "old_xp": old_xp,
                "new_xp": new_xp,
                "old_level": old_level,
                "new_level": new_level,
            }, headers={"Access-Control-Allow-Origin": "*"})

        except Exception as e:
            logger.error_tree("XP Set API Error", e, [
                ("ID", str(user_id)),
                ("XP", str(new_xp)),
                ("Client IP", client_ip),
            ])
            # Don't expose internal error details to clients (may contain secrets)
            return web.json_response(
                {"error": "Internal server error"},
                status=500,
                headers={"Access-Control-Allow-Origin": "*"}
            )

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
                    tomorrow += timedelta(days=1)
                seconds_until_midnight = (tomorrow - now_est).total_seconds()

                logger.tree("Midnight Booster Refresh Scheduled", [
                    ("Next Run", tomorrow.strftime("%Y-%m-%d %H:%M:%S EST")),
                    ("Wait Time", f"{int(seconds_until_midnight // 3600)}h {int((seconds_until_midnight % 3600) // 60)}m"),
                ], emoji="⏰")

                await asyncio.sleep(seconds_until_midnight)

                # Run the refresh
                await self._refresh_all_booster_status()

            except asyncio.CancelledError:
                logger.tree("Midnight Booster Refresh", [
                    ("Status", "Task cancelled"),
                ], emoji="⏹️")
                break
            except Exception as e:
                logger.error_tree("Midnight Refresh Scheduler Error", e)
                # Wait an hour before retrying on error
                await asyncio.sleep(3600)

    async def _daily_xp_snapshot(self) -> None:
        """Create daily XP snapshots at midnight UTC for period-based leaderboards."""
        from datetime import timezone

        while True:
            try:
                # Calculate seconds until next midnight UTC
                now_utc = datetime.now(timezone.utc)
                tomorrow_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
                if now_utc.hour >= 0:
                    tomorrow_utc += timedelta(days=1)
                seconds_until_midnight = (tomorrow_utc - now_utc).total_seconds()

                logger.tree("XP Snapshot Scheduled", [
                    ("Next Run", tomorrow_utc.strftime("%Y-%m-%d %H:%M:%S UTC")),
                    ("Wait Time", f"{int(seconds_until_midnight // 3600)}h {int((seconds_until_midnight % 3600) // 60)}m"),
                ], emoji="📸")

                await asyncio.sleep(seconds_until_midnight)

                # Create snapshot in thread to avoid blocking
                snapshot_count = await asyncio.to_thread(db.create_daily_snapshot)

                # Cleanup old snapshots (keep 35 days for monthly leaderboards)
                deleted = await asyncio.to_thread(db.cleanup_old_snapshots, 35)

                logger.tree("Daily XP Snapshot Complete", [
                    ("Users Snapshotted", str(snapshot_count)),
                    ("Old Snapshots Deleted", str(deleted)),
                ], emoji="✅")

            except asyncio.CancelledError:
                logger.tree("XP Snapshot Task", [
                    ("Status", "Task cancelled"),
                ], emoji="⏹️")
                break
            except Exception as e:
                logger.error_tree("XP Snapshot Scheduler Error", e)
                # Wait an hour before retrying on error
                await asyncio.sleep(3600)

    async def _refresh_all_booster_status(self) -> None:
        """Refresh booster status for all cached users. Non-blocking with staggered checks."""
        global _avatar_cache, _response_cache

        if not self._bot or not self._bot.is_ready():
            logger.tree("Booster Refresh Skipped", [
                ("Reason", "Bot not ready"),
            ], emoji="⚠️")
            return

        from src.core.config import config
        guild = self._bot.get_guild(config.GUILD_ID)
        if not guild:
            logger.tree("Booster Refresh Skipped", [
                ("Reason", "Guild not found"),
            ], emoji="⚠️")
            return

        start_time = time.time()

        # Copy keys under lock to avoid race condition
        async with _avatar_cache_lock:
            cached_user_ids = list(_avatar_cache.keys())
        total_users = len(cached_user_ids)

        if total_users == 0:
            logger.tree("Booster Refresh Skipped", [
                ("Reason", "No users in cache"),
            ], emoji="ℹ️")
            return

        logger.tree("Midnight Booster Refresh Started", [
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
                        async with _avatar_cache_lock:
                            if user_id in _avatar_cache:
                                del _avatar_cache[user_id]
                        continue

                # Check current booster status
                current_is_booster = member.premium_since is not None

                # Get cached status under lock
                async with _avatar_cache_lock:
                    if user_id in _avatar_cache:
                        cached_data = _avatar_cache[user_id]
                        cached_is_booster = cached_data[4] if len(cached_data) > 4 else False

                        if current_is_booster != cached_is_booster:
                            # Status changed - update cache
                            display_name = member.global_name or member.display_name or member.name
                            username = member.name
                            # Prefer guild avatar (server-specific), fall back to global avatar
                            if member.guild_avatar:
                                avatar_url = member.guild_avatar.url
                            elif member.avatar:
                                avatar_url = member.avatar.url
                            else:
                                avatar_url = member.default_avatar.url
                            joined_at = int(member.joined_at.timestamp()) if member.joined_at else None

                            _avatar_cache[user_id] = (avatar_url, display_name, username, joined_at, current_is_booster)
                            updated += 1

                            logger.tree("Booster Status Updated", [
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
                    logger.tree("Booster Check Error", [
                        ("ID", str(user_id)),
                        ("Error", str(e)[:50]),
                    ], emoji="⚠️")

        # Clear response cache if any updates occurred
        if updated > 0:
            _response_cache.clear()

        elapsed = round(time.time() - start_time, 2)

        logger.tree("Midnight Booster Refresh Complete", [
            ("Total Checked", str(total_users)),
            ("Updated", str(updated)),
            ("Unchanged", str(unchanged)),
            ("Errors", str(errors)),
            ("Duration", f"{elapsed}s"),
        ], emoji="✅")

    async def _bootstrap_snapshots(self) -> None:
        """Create initial XP snapshot if none exist, enabling period leaderboards immediately."""
        from datetime import timezone

        try:
            # Check if any snapshots exist for yesterday (needed for "today" period)
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

            with db._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT COUNT(*) as count FROM xp_snapshots
                    WHERE guild_id = ? AND date = ?
                """, (config.GUILD_ID, yesterday))
                row = cur.fetchone()
                has_yesterday = row["count"] > 0 if row else False

            if not has_yesterday:
                # Create a snapshot dated yesterday so "today" period works
                # This is a bootstrap - actual XP gained will be tracked after first midnight
                logger.tree("XP Snapshot Bootstrap", [
                    ("Status", "Creating initial snapshot"),
                    ("Date", yesterday),
                ], emoji="🔧")

                with db._get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT OR IGNORE INTO xp_snapshots
                            (user_id, guild_id, date, xp_total, level, total_messages, voice_minutes)
                        SELECT
                            user_id, guild_id, ?, xp, level, total_messages, voice_minutes
                        FROM user_xp
                        WHERE guild_id = ? AND is_active = 1
                    """, (yesterday, config.GUILD_ID))
                    count = cur.rowcount

                logger.tree("XP Snapshot Bootstrap Complete", [
                    ("Users", str(count)),
                    ("Date", yesterday),
                ], emoji="✅")
            else:
                logger.tree("XP Snapshots Found", [
                    ("Status", "Period leaderboards ready"),
                ], emoji="📸")

        except Exception as e:
            logger.error_tree("XP Snapshot Bootstrap Error", e)

    async def setup(self) -> None:
        """Initialize and start the API server."""
        self._start_time = datetime.now(DAMASCUS_TZ)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        site = web.TCPSite(self.runner, STATS_API_HOST, STATS_API_PORT)
        await site.start()

        # Bootstrap XP snapshots if none exist (enables period leaderboards immediately)
        await self._bootstrap_snapshots()

        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self._midnight_task = asyncio.create_task(self._midnight_booster_refresh())
        self._snapshot_task = asyncio.create_task(self._daily_xp_snapshot())

        logger.tree("Syria API Ready", [
            ("Host", STATS_API_HOST),
            ("Port", str(STATS_API_PORT)),
            ("Endpoints", "/api/syria/leaderboard, /api/syria/user/{id}, /api/syria/stats"),
            ("Rate Limit", "60 req/min"),
            ("Midnight Refresh", "Enabled"),
            ("Daily Snapshots", "Enabled (UTC midnight)"),
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

        if hasattr(self, '_snapshot_task') and self._snapshot_task:
            self._snapshot_task.cancel()
            try:
                await self._snapshot_task
            except asyncio.CancelledError:
                pass

        if self.runner:
            await self.runner.cleanup()
            logger.tree("Syria API Stopped", [
                ("Status", "Shutdown complete"),
            ], emoji="🛑")


__all__ = ["SyriaAPI", "STATS_API_PORT"]
