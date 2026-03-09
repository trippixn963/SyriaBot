"""
SyriaBot - Social Media Monitor Service
=======================================

Monitors TikTok and Instagram accounts for new posts using yt-dlp
and sends notifications to a Discord channel with video thumbnails.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional, TypedDict

import discord
from discord import ui

from src.core.config import config
from src.core.colors import COLOR_GOLD, COLOR_SUCCESS
from src.core.emojis import EMOJI_TIKTOK_ID, EMOJI_INSTAGRAM_ID, EMOJI_TIKTOK, EMOJI_INSTAGRAM
from src.core.logger import logger
from src.services.database import db
from src.utils.async_utils import create_safe_task

if TYPE_CHECKING:
    from src.bot import SyriaBot


# =============================================================================
# Type Definitions
# =============================================================================

class VideoInfo(TypedDict):
    """Type definition for video information from yt-dlp."""
    id: str
    title: str
    url: str
    thumbnail: str
    uploader: str


class StoredData(TypedDict):
    """Type definition for persisted data."""
    tiktok: list[str]
    instagram: list[str]


# =============================================================================
# Views
# =============================================================================

class SocialLinkView(ui.View):
    """Persistent view with a link button to the social media post."""

    def __init__(self, url: str, platform: str) -> None:
        super().__init__(timeout=None)

        if platform == "tiktok":
            emoji = discord.PartialEmoji.from_str(EMOJI_TIKTOK_ID)
            label = "Watch on TikTok"
        else:
            emoji = discord.PartialEmoji.from_str(EMOJI_INSTAGRAM_ID)
            label = "View on Instagram"

        self.add_item(ui.Button(
            style=discord.ButtonStyle.secondary,
            label=label,
            emoji=emoji,
            url=url,
        ))


# =============================================================================
# Service
# =============================================================================

class SocialMonitorService:
    """
    Service for monitoring social media accounts and posting to Discord.

    Features:
    - Monitors TikTok and Instagram profiles for new posts
    - Posts Discord embeds with video thumbnails
    - Persists posted IDs to avoid duplicates across restarts
    - First-run detection to avoid spamming old videos
    """

    # Theme colors
    TIKTOK_COLOR: int = COLOR_GOLD
    INSTAGRAM_COLOR: int = COLOR_SUCCESS

    # Timing
    CHECK_INTERVAL: int = 300  # 5 minutes
    INITIAL_DELAY: int = 30   # Wait before first check
    ERROR_RETRY_DELAY: int = 60
    FETCH_TIMEOUT: int = 90

    # Data persistence
    _JSON_FILE: Path = Path(__file__).parent.parent.parent.parent / "data" / "social_posts.json"
    MAX_STORED_IDS: int = 100
    MAX_VIDEOS_TO_CHECK: int = 10

    def __init__(self, bot: SyriaBot) -> None:
        """
        Initialize the Social Monitor service.

        Args:
            bot: The SyriaBot instance
        """
        self.bot: SyriaBot = bot
        self._task: Optional[asyncio.Task[None]] = None
        self._running: bool = False
        self._posted_tiktok: set[str] = set()
        self._posted_instagram: set[str] = set()
        self._first_run_tiktok: bool = True
        self._first_run_instagram: bool = True
        self._load_data()

    # =========================================================================
    # Data Persistence
    # =========================================================================

    def _load_data(self) -> None:
        """Load posted video IDs from database, migrating from JSON if needed."""
        self._migrate_json()

        self._posted_tiktok = db.social_get_posted_ids("tiktok")
        self._posted_instagram = db.social_get_posted_ids("instagram")

        # If we have stored data, this isn't the first run
        if self._posted_tiktok:
            self._first_run_tiktok = False
        if self._posted_instagram:
            self._first_run_instagram = False

        logger.tree("Social Monitor Data Loaded", [
            ("TikTok IDs", str(len(self._posted_tiktok))),
            ("Instagram IDs", str(len(self._posted_instagram))),
            ("First Run TikTok", str(self._first_run_tiktok)),
            ("First Run Instagram", str(self._first_run_instagram)),
        ], emoji="📂")

    def _migrate_json(self) -> None:
        """One-time migration from JSON file to SQLite."""
        if not self._JSON_FILE.exists():
            return

        try:
            with open(self._JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                self._JSON_FILE.rename(self._JSON_FILE.with_suffix(".json.migrated"))
                return

            for video_id in data.get("tiktok", []):
                db.social_add_posted_id("tiktok", video_id)
            for video_id in data.get("instagram", []):
                db.social_add_posted_id("instagram", video_id)

            self._JSON_FILE.rename(self._JSON_FILE.with_suffix(".json.migrated"))

            logger.tree("Social Monitor Data Migrated", [
                ("From", "JSON"),
                ("To", "SQLite"),
                ("TikTok", str(len(data.get("tiktok", [])))),
                ("Instagram", str(len(data.get("instagram", [])))),
            ], emoji="🔄")

        except Exception as e:
            logger.error_tree("Social Monitor JSON Migration Failed", e, [
                ("File", str(self._JSON_FILE)),
            ])

    def _save_data(self) -> None:
        """Persist current posted IDs and clean up old entries."""
        # Add any new IDs that are in memory but not yet in DB
        # (individual adds happen in _check_tiktok/_check_instagram)
        db.social_cleanup("tiktok", self.MAX_STORED_IDS)
        db.social_cleanup("instagram", self.MAX_STORED_IDS)

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def setup(self) -> None:
        """Initialize and start the monitoring service."""
        if not config.SOCIAL_MONITOR_CH:
            logger.tree("Social Monitor", [
                ("Status", "Disabled"),
                ("Reason", "SYRIA_SOCIAL_CH not set"),
            ], emoji="info")
            return

        if not config.TIKTOK_USERNAME and not config.INSTAGRAM_USERNAME:
            logger.tree("Social Monitor", [
                ("Status", "Disabled"),
                ("Reason", "No accounts configured"),
            ], emoji="info")
            return

        self._running = True
        self._task = create_safe_task(self._monitor_loop(), "Social Monitor Loop")

        accounts: list[str] = []
        if config.TIKTOK_USERNAME:
            accounts.append(f"TikTok: @{config.TIKTOK_USERNAME}")
        if config.INSTAGRAM_USERNAME:
            accounts.append(f"IG: @{config.INSTAGRAM_USERNAME}")

        logger.tree("Social Monitor", [
            ("Status", "Started"),
            ("Channel", str(config.SOCIAL_MONITOR_CH)),
            ("Accounts", ", ".join(accounts)),
            ("Interval", f"{self.CHECK_INTERVAL}s"),
        ], emoji="check")

    def stop(self) -> None:
        """Stop the monitoring service gracefully."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        logger.tree("Social Monitor", [
            ("Status", "Stopped"),
        ], emoji="stop")

    # =========================================================================
    # Monitor Loop
    # =========================================================================

    async def _monitor_loop(self) -> None:
        """Main monitoring loop that periodically checks for new posts."""
        await asyncio.sleep(self.INITIAL_DELAY)

        while self._running:
            try:
                if config.TIKTOK_USERNAME:
                    await self._check_tiktok()

                if config.INSTAGRAM_USERNAME:
                    await self._check_instagram()

                logger.tree("Social Monitor", [
                    ("Status", "Check complete"),
                    ("Next", f"{self.CHECK_INTERVAL}s"),
                ], emoji="clock")

                await asyncio.sleep(self.CHECK_INTERVAL)

            except asyncio.CancelledError:
                logger.tree("Social Monitor", [
                    ("Status", "Loop cancelled"),
                ], emoji="info")
                break
            except Exception as e:
                logger.error_tree("Social Monitor Loop Error", e, [
                    ("Recovery", f"Retrying in {self.ERROR_RETRY_DELAY}s"),
                ])
                await asyncio.sleep(self.ERROR_RETRY_DELAY)

    # =========================================================================
    # Video Fetching
    # =========================================================================

    async def _fetch_video_list(self, url: str, platform: str) -> list[str]:
        """
        Fetch list of video IDs from a profile using yt-dlp flat-playlist.

        Args:
            url: The profile URL to fetch
            platform: Platform name for logging

        Returns:
            List of video IDs
        """
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--dump-json",
            "--no-warnings",
            "--quiet",
            "--playlist-end", str(self.MAX_VIDEOS_TO_CHECK),
            url
        ]

        logger.tree("Social Monitor", [
            ("Action", "Fetching video list"),
            ("Platform", platform.title()),
            ("URL", url),
        ], emoji="search")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.FETCH_TIMEOUT
            )

            if proc.returncode != 0:
                error_msg = stderr.decode().strip()[:150] if stderr else "Unknown error"
                logger.tree("Social Monitor", [
                    ("Status", "Fetch failed"),
                    ("Platform", platform.title()),
                    ("Exit Code", str(proc.returncode)),
                    ("Error", error_msg),
                ], emoji="warn")
                return []

            video_ids: list[str] = []
            for line in stdout.decode().strip().split("\n"):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    video_id = data.get("id", "")
                    if video_id:
                        video_ids.append(video_id)
                except json.JSONDecodeError:
                    continue

            logger.tree("Social Monitor", [
                ("Status", "Video list fetched"),
                ("Platform", platform.title()),
                ("Videos", str(len(video_ids))),
            ], emoji="check")

            return video_ids

        except asyncio.TimeoutError:
            logger.tree("Social Monitor", [
                ("Status", "Fetch timeout"),
                ("Platform", platform.title()),
                ("Timeout", f"{self.FETCH_TIMEOUT}s"),
            ], emoji="warn")
            return []
        except FileNotFoundError:
            logger.error_tree("Social Monitor Error", Exception("yt-dlp not found"), [
                ("Platform", platform.title()),
                ("Hint", "Install yt-dlp: pip install yt-dlp"),
            ])
            return []
        except Exception as e:
            logger.error_tree("Social Monitor Fetch Error", e, [
                ("Platform", platform.title()),
                ("URL", url),
            ])
            return []

    async def _fetch_video_info(self, url: str, platform: str) -> Optional[VideoInfo]:
        """
        Fetch full video information including thumbnail.

        Args:
            url: The video URL to fetch
            platform: Platform name for logging

        Returns:
            VideoInfo dict or None if fetch failed
        """
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-warnings",
            "--quiet",
            "--no-download",
            url
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.FETCH_TIMEOUT
            )

            if proc.returncode != 0:
                error_msg = stderr.decode().strip()[:100] if stderr else "Unknown"
                logger.tree("Social Monitor", [
                    ("Status", "Video info fetch failed"),
                    ("Platform", platform.title()),
                    ("Error", error_msg),
                ], emoji="warn")
                return None

            data = json.loads(stdout.decode().strip())

            # Extract thumbnail - try multiple fields
            thumbnail = (
                data.get("thumbnail") or
                data.get("thumbnails", [{}])[-1].get("url", "") or
                ""
            )

            return VideoInfo(
                id=data.get("id", ""),
                title=data.get("title", "") or data.get("description", "")[:200] or "",
                url=data.get("webpage_url", "") or data.get("url", ""),
                thumbnail=thumbnail,
                uploader=data.get("uploader", "") or data.get("channel", ""),
            )

        except asyncio.TimeoutError:
            logger.tree("Social Monitor", [
                ("Status", "Video info timeout"),
                ("Platform", platform.title()),
            ], emoji="warn")
            return None
        except json.JSONDecodeError as e:
            logger.error_tree("Social Monitor JSON Error", e, [
                ("Platform", platform.title()),
            ])
            return None
        except Exception as e:
            logger.error_tree("Social Monitor Video Info Error", e, [
                ("Platform", platform.title()),
            ])
            return None

    # =========================================================================
    # Platform Checks
    # =========================================================================

    async def _check_tiktok(self) -> None:
        """Check TikTok for new videos."""
        username = config.TIKTOK_USERNAME.lstrip("@")
        profile_url = f"https://www.tiktok.com/@{username}"

        video_ids = await self._fetch_video_list(profile_url, "tiktok")
        if not video_ids:
            return

        new_count = 0
        for video_id in video_ids:
            if not video_id or video_id in self._posted_tiktok:
                continue

            self._posted_tiktok.add(video_id)
            db.social_add_posted_id("tiktok", video_id)

            # Only post notifications after first run
            if not self._first_run_tiktok:
                video_url = f"https://www.tiktok.com/@{username}/video/{video_id}"

                logger.tree("Social Monitor", [
                    ("Action", "Fetching new video info"),
                    ("Platform", "TikTok"),
                    ("Video ID", video_id),
                ], emoji="download")

                video_info = await self._fetch_video_info(video_url, "tiktok")
                if video_info:
                    await self._post_notification("tiktok", video_info, username)
                    new_count += 1
                else:
                    # Fallback: post without thumbnail
                    fallback_info = VideoInfo(
                        id=video_id,
                        title="",
                        url=video_url,
                        thumbnail="",
                        uploader=username,
                    )
                    await self._post_notification("tiktok", fallback_info, username)
                    new_count += 1

        if self._first_run_tiktok:
            logger.tree("Social Monitor", [
                ("Platform", "TikTok"),
                ("Status", "Initialized"),
                ("Cached", f"{len(video_ids)} videos"),
            ], emoji="info")
            self._first_run_tiktok = False

        if new_count > 0:
            logger.tree("Social Monitor", [
                ("Platform", "TikTok"),
                ("New Posts", str(new_count)),
            ], emoji="bell")

        self._save_data()

    async def _check_instagram(self) -> None:
        """Check Instagram for new posts."""
        username = config.INSTAGRAM_USERNAME.lstrip("@")
        profile_url = f"https://www.instagram.com/{username}/"

        video_ids = await self._fetch_video_list(profile_url, "instagram")
        if not video_ids:
            return

        new_count = 0
        for video_id in video_ids:
            if not video_id or video_id in self._posted_instagram:
                continue

            self._posted_instagram.add(video_id)
            db.social_add_posted_id("instagram", video_id)

            if not self._first_run_instagram:
                post_url = f"https://www.instagram.com/p/{video_id}/"

                logger.tree("Social Monitor", [
                    ("Action", "Fetching new post info"),
                    ("Platform", "Instagram"),
                    ("Post ID", video_id),
                ], emoji="download")

                video_info = await self._fetch_video_info(post_url, "instagram")
                if video_info:
                    await self._post_notification("instagram", video_info, username)
                    new_count += 1
                else:
                    fallback_info = VideoInfo(
                        id=video_id,
                        title="",
                        url=post_url,
                        thumbnail="",
                        uploader=username,
                    )
                    await self._post_notification("instagram", fallback_info, username)
                    new_count += 1

        if self._first_run_instagram:
            logger.tree("Social Monitor", [
                ("Platform", "Instagram"),
                ("Status", "Initialized"),
                ("Cached", f"{len(video_ids)} posts"),
            ], emoji="info")
            self._first_run_instagram = False

        if new_count > 0:
            logger.tree("Social Monitor", [
                ("Platform", "Instagram"),
                ("New Posts", str(new_count)),
            ], emoji="bell")

        self._save_data()

    # =========================================================================
    # Discord Posting
    # =========================================================================

    async def _post_notification(
        self,
        platform: str,
        post: VideoInfo,
        username: str
    ) -> None:
        """
        Post a notification embed to the Discord channel.

        Args:
            platform: "tiktok" or "instagram"
            post: Video information
            username: Account username
        """
        channel = self.bot.get_channel(config.SOCIAL_MONITOR_CH)
        if channel is None:
            logger.tree("Social Monitor", [
                ("Status", "Channel not found"),
                ("Channel ID", str(config.SOCIAL_MONITOR_CH)),
            ], emoji="warn")
            return

        if not isinstance(channel, discord.TextChannel):
            logger.tree("Social Monitor", [
                ("Status", "Invalid channel type"),
                ("Channel ID", str(config.SOCIAL_MONITOR_CH)),
                ("Type", type(channel).__name__),
            ], emoji="warn")
            return

        try:
            # Platform-specific config
            if platform == "tiktok":
                color = self.TIKTOK_COLOR
                platform_name = "TikTok"
                platform_emoji = EMOJI_TIKTOK
                profile_url = f"https://tiktok.com/@{username}"
                video_url = post["url"] or f"https://www.tiktok.com/@{username}/video/{post['id']}"
            else:
                color = self.INSTAGRAM_COLOR
                platform_name = "Instagram"
                platform_emoji = EMOJI_INSTAGRAM
                profile_url = f"https://instagram.com/{username}"
                video_url = post["url"] or f"https://www.instagram.com/p/{post['id']}/"

            # Build description
            description = post["title"][:500] if post["title"] else "Check out our latest post!"

            # Create embed
            embed = discord.Embed(
                title=f"{platform_emoji} New {platform_name} Post!",
                description=description,
                url=video_url,
                color=color,
                timestamp=datetime.now(timezone.utc),
            )

            # Set thumbnail/image if available
            if post["thumbnail"]:
                embed.set_image(url=post["thumbnail"])

            # Create view with link button
            view = SocialLinkView(url=video_url, platform=platform)

            # Send the notification
            await channel.send(embed=embed, view=view)

            logger.tree("Social Monitor", [
                ("Status", "Notification posted"),
                ("Platform", platform_name),
                ("Account", f"@{username}"),
                ("Video ID", post["id"]),
                ("Channel", f"#{channel.name}"),
                ("Has Thumbnail", str(bool(post["thumbnail"]))),
            ], emoji="check")

            # Send ping to general chat
            await self._notify_general_chat(platform_name, platform_emoji, platform, video_url, channel.id)

        except discord.Forbidden as e:
            logger.error_tree("Social Monitor Post Error", e, [
                ("Reason", "Missing permissions"),
                ("Channel", str(config.SOCIAL_MONITOR_CH)),
            ])
        except discord.HTTPException as e:
            logger.error_tree("Social Monitor Post Error", e, [
                ("Reason", "Discord API error"),
                ("Status", str(e.status)),
            ])
        except Exception as e:
            logger.error_tree("Social Monitor Post Error", e, [
                ("Platform", platform),
                ("Video ID", post.get("id", "unknown")),
            ])

    async def _notify_general_chat(
        self,
        platform_name: str,
        platform_emoji: str,
        platform: str,
        video_url: str,
        socials_channel_id: int
    ) -> None:
        """
        Send a notification to general chat about a new social media post.

        Args:
            platform_name: "TikTok" or "Instagram"
            platform_emoji: The platform emoji string
            platform: "tiktok" or "instagram" for the view
            video_url: Direct URL to the post
            socials_channel_id: The socials channel ID to link to
        """
        if not config.GENERAL_CHANNEL_ID:
            return

        general_channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
        if general_channel is None or not isinstance(general_channel, discord.TextChannel):
            return

        try:
            message = f"{platform_emoji} **New {platform_name} post!** Check it out in <#{socials_channel_id}>"
            view = SocialLinkView(url=video_url, platform=platform)
            await general_channel.send(message, view=view)

            logger.tree("Social Monitor", [
                ("Status", "General chat notified"),
                ("Channel", f"#{general_channel.name}"),
            ], emoji="bell")

        except discord.Forbidden:
            logger.tree("Social Monitor", [
                ("Status", "Cannot send to general"),
                ("Reason", "Missing permissions"),
            ], emoji="warn")
        except Exception as e:
            logger.error_tree("Social Monitor General Notify Error", e)
