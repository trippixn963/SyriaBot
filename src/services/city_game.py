"""
SyriaBot - City Guessing Game
=============================

Dead chat reviver that shows Syrian city images for users to guess.

Features:
- Triggers after 30 min of chat inactivity
- Uses curated local images (assets/cities/)
- First correct guess wins 1k XP
- 10 minute time limit per game

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import os
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Dict, List, Set

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.core.config import config
from src.core.colors import COLOR_SYRIA_GREEN
from src.core.logger import log
from src.utils.footer import set_footer

if TYPE_CHECKING:
    from src.bot import SyriaBot


# Path to city images
ASSETS_PATH = Path(__file__).parent.parent.parent / "assets" / "cities"


# =============================================================================
# Configuration
# =============================================================================

DEAD_CHAT_ROLE_ID = config.DEAD_CHAT_ROLE_ID
INACTIVITY_THRESHOLD = 30 * 60  # 30 minutes in seconds
GUESS_TIME_LIMIT = 10 * 60  # 10 minutes in seconds
XP_REWARD = 1000
GAME_COOLDOWN = 60 * 60  # 1 hour cooldown between games


# =============================================================================
# Syrian Governorates Data (14 Governorates)
# =============================================================================

SYRIAN_GOVERNORATES = [
    {
        "english": "Damascus",
        "arabic": "دمشق",
        "aliases": ["dimashq", "sham", "الشام"],
        "folder": "damascus",
    },
    {
        "english": "Rif Dimashq",
        "arabic": "ريف دمشق",
        "aliases": ["rif dimashq", "damascus countryside", "ريف الشام"],
        "folder": "rif_dimashq",
    },
    {
        "english": "Aleppo",
        "arabic": "حلب",
        "aliases": ["halab"],
        "folder": "aleppo",
    },
    {
        "english": "Homs",
        "arabic": "حمص",
        "aliases": ["hims"],
        "folder": "homs",
    },
    {
        "english": "Hama",
        "arabic": "حماة",
        "aliases": ["hamah", "حماه"],
        "folder": "hama",
    },
    {
        "english": "Latakia",
        "arabic": "اللاذقية",
        "aliases": ["lattakia", "al-ladhiqiyah", "اللازقية"],
        "folder": "latakia",
    },
    {
        "english": "Tartus",
        "arabic": "طرطوس",
        "aliases": ["tartous"],
        "folder": "tartus",
    },
    {
        "english": "Idlib",
        "arabic": "إدلب",
        "aliases": ["adlib", "ادلب"],
        "folder": "idlib",
    },
    {
        "english": "Deir ez-Zor",
        "arabic": "دير الزور",
        "aliases": ["deir ezzor", "deir al-zor", "دير ازور"],
        "folder": "deir_ez_zor",
    },
    {
        "english": "Raqqa",
        "arabic": "الرقة",
        "aliases": ["ar-raqqah", "rakka", "الرقه"],
        "folder": "raqqa",
    },
    {
        "english": "Hasakah",
        "arabic": "الحسكة",
        "aliases": ["al-hasakah", "hasaka", "الحسكه"],
        "folder": "hasakah",
    },
    {
        "english": "Daraa",
        "arabic": "درعا",
        "aliases": ["deraa", "dar'a"],
        "folder": "daraa",
    },
    {
        "english": "Sweida",
        "arabic": "السويداء",
        "aliases": ["suwayda", "as-suwayda", "السويدا"],
        "folder": "sweida",
    },
    {
        "english": "Quneitra",
        "arabic": "القنيطرة",
        "aliases": ["kuneitra", "al-quneitra", "القنيطره"],
        "folder": "quneitra",
    },
]


# =============================================================================
# City Game Service
# =============================================================================

class CityGameService:
    """Service for the Syrian city guessing game."""

    def __init__(self, bot: "SyriaBot") -> None:
        self.bot = bot
        self._last_message_time: float = time.time()
        self._game_active: bool = False
        self._current_city: Optional[Dict] = None
        self._game_message: Optional[discord.Message] = None
        self._game_start_time: float = 0
        self._last_game_time: float = 0
        self._timeout_task: Optional[asyncio.Task] = None
        self._recently_used: List[str] = []  # Track recently used cities

    async def setup(self) -> None:
        """Initialize the city game service."""
        self._last_message_time = time.time()

        # Start the inactivity checker
        self.inactivity_check.start()

        log.tree("City Game Service Ready", [
            ("Channel", str(config.GENERAL_CHANNEL_ID)),
            ("Role", str(DEAD_CHAT_ROLE_ID)),
            ("Inactivity", f"{INACTIVITY_THRESHOLD // 60} min"),
            ("Time Limit", f"{GUESS_TIME_LIMIT // 60} min"),
            ("Reward", f"{XP_REWARD:,} XP"),
            ("Governorates", str(len(SYRIAN_GOVERNORATES))),
        ], emoji="🏙️")

    def stop(self) -> None:
        """Stop the city game service."""
        if self.inactivity_check.is_running():
            self.inactivity_check.cancel()
        # Cancel any running timeout task
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
        log.tree("City Game Service Stopped", [], emoji="🛑")

    async def close(self) -> None:
        """Clean up resources."""
        self.stop()

    def on_message(self, channel_id: int) -> None:
        """Update last message time when a message is sent in the tracked channel."""
        if channel_id == config.GENERAL_CHANNEL_ID:
            self._last_message_time = time.time()

    @tasks.loop(minutes=5)
    async def inactivity_check(self) -> None:
        """Check for chat inactivity and start a game if needed."""
        if self._game_active:
            return

        now = time.time()

        # Check cooldown
        if now - self._last_game_time < GAME_COOLDOWN:
            return

        # Check inactivity
        if now - self._last_message_time < INACTIVITY_THRESHOLD:
            return

        # Start a game
        await self._start_game()

    @inactivity_check.before_loop
    async def before_inactivity_check(self) -> None:
        """Wait for bot to be ready."""
        await self.bot.wait_until_ready()

    def _get_random_image_from_folder(self, folder_name: str) -> Optional[Path]:
        """Get a random image from a city's folder."""
        folder_path = ASSETS_PATH / folder_name
        if not folder_path.exists() or not folder_path.is_dir():
            return None

        # Get all image files in folder
        valid_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        images = [
            f for f in folder_path.iterdir()
            if f.is_file() and f.suffix.lower() in valid_extensions
        ]

        if not images:
            return None

        return random.choice(images)

    def _get_random_city(self) -> Dict:
        """Get a random city that hasn't been used recently."""
        available = [c for c in SYRIAN_GOVERNORATES if c["english"] not in self._recently_used]

        if not available:
            # Reset if all cities used
            self._recently_used = []
            available = SYRIAN_GOVERNORATES

        city = random.choice(available)
        self._recently_used.append(city["english"])

        # Keep only last 10 in recent list
        if len(self._recently_used) > 10:
            self._recently_used = self._recently_used[-10:]

        return city

    async def _start_game(self, manual: bool = False) -> bool:
        """Start a new city guessing game. Returns True if game started."""
        channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            log.tree("City Game Channel Not Found", [
                ("Channel ID", str(config.GENERAL_CHANNEL_ID)),
            ], emoji="⚠️")
            return False

        # Select a city
        city = self._get_random_city()

        # Get random image from city folder
        image_path = self._get_random_image_from_folder(city["folder"])
        if not image_path:
            log.tree("City Game Skipped", [
                ("City", city["english"]),
                ("Folder", city["folder"]),
                ("Reason", "No images in folder"),
            ], emoji="⚠️")
            return False

        self._game_active = True
        self._current_city = city
        self._game_start_time = time.time()

        # Build embed
        embed = discord.Embed(
            title="🏙️ Guess the Syrian City!",
            description=(
                f"<@&{DEAD_CHAT_ROLE_ID}> Chat has been quiet!\n\n"
                f"**Can you name this Syrian city?**\n"
                f"First correct answer wins **{XP_REWARD:,} XP**!\n\n"
                f"*Time limit: {GUESS_TIME_LIMIT // 60} minutes*"
            ),
            color=COLOR_SYRIA_GREEN
        )
        # Use attachment for local image
        embed.set_image(url=f"attachment://{image_path.name}")
        set_footer(embed)

        try:
            # Create file attachment from local image
            file = discord.File(image_path, filename=image_path.name)

            self._game_message = await channel.send(
                content=f"<@&{DEAD_CHAT_ROLE_ID}>",
                embed=embed,
                file=file,
                allowed_mentions=discord.AllowedMentions(roles=True)
            )

            trigger = "Manual" if manual else "Inactivity"
            log.tree("City Game Started", [
                ("City", city["english"]),
                ("Arabic", city["arabic"]),
                ("Channel", channel.name),
                ("Trigger", trigger),
            ], emoji="🏙️")

            # Start timeout task (and store reference for cleanup)
            self._timeout_task = asyncio.create_task(self._game_timeout())
            return True

        except Exception as e:
            self._game_active = False
            self._current_city = None
            log.error_tree("City Game Start Failed", e)
            return False

    async def _game_timeout(self) -> None:
        """Handle game timeout after time limit."""
        await asyncio.sleep(GUESS_TIME_LIMIT)

        if not self._game_active or not self._current_city:
            return

        await self._end_game(winner=None, timed_out=True)

    async def check_guess(self, message: discord.Message) -> bool:
        """
        Check if a message is a correct guess.

        Returns True if the game ended (correct guess).
        """
        if not self._game_active or not self._current_city:
            return False

        if message.channel.id != config.GENERAL_CHANNEL_ID:
            return False

        if message.author.bot:
            return False

        guess = message.content.strip().lower()
        city = self._current_city

        # Check all valid answers
        valid_answers = [
            city["english"].lower(),
            city["arabic"],
        ]
        valid_answers.extend([a.lower() for a in city.get("aliases", [])])

        if guess in valid_answers:
            await self._end_game(winner=message.author, timed_out=False)
            return True

        return False

    async def _end_game(self, winner: Optional[discord.Member], timed_out: bool) -> None:
        """End the current game."""
        if not self._current_city:
            return

        city = self._current_city
        channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)

        self._game_active = False
        self._last_game_time = time.time()

        # Cancel timeout task if game ended early (correct guess)
        if not timed_out and self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            self._timeout_task = None

        if timed_out:
            # No winner
            embed = discord.Embed(
                title="⏰ Time's Up!",
                description=(
                    f"Nobody guessed the city!\n\n"
                    f"**Answer:** {city['english']} ({city['arabic']})"
                ),
                color=COLOR_SYRIA_GREEN
            )
            set_footer(embed)

            if channel:
                await channel.send(embed=embed)

            log.tree("City Game Timeout", [
                ("City", city["english"]),
                ("Duration", f"{GUESS_TIME_LIMIT // 60} min"),
            ], emoji="⏰")

        elif winner:
            # Grant XP
            xp_granted = False
            if self.bot.xp_service and isinstance(winner, discord.Member):
                try:
                    await self.bot.xp_service._grant_xp(winner, XP_REWARD, "city_game")
                    xp_granted = True
                except Exception as e:
                    log.tree("City Game XP Grant Failed", [
                        ("Winner", winner.name),
                        ("Error", str(e)[:50]),
                    ], emoji="⚠️")

            # Calculate time taken
            time_taken = int(time.time() - self._game_start_time)
            minutes = time_taken // 60
            seconds = time_taken % 60
            time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

            embed = discord.Embed(
                title="🎉 Correct!",
                description=(
                    f"{winner.mention} guessed it in **{time_str}**!\n\n"
                    f"**Answer:** {city['english']} ({city['arabic']})\n"
                    f"**Reward:** +{XP_REWARD:,} XP"
                ),
                color=COLOR_SYRIA_GREEN
            )
            embed.set_thumbnail(url=winner.display_avatar.url)
            set_footer(embed)

            if channel:
                await channel.send(embed=embed)

            log.tree("City Game Won", [
                ("Winner", f"{winner.name} ({winner.display_name})"),
                ("Winner ID", str(winner.id)),
                ("City", city["english"]),
                ("Time", time_str),
                ("XP Granted", str(xp_granted)),
            ], emoji="🏆")

        self._current_city = None
        self._game_message = None

    async def manual_start(self) -> tuple[bool, str]:
        """
        Manually trigger a city game (for admin testing).

        Returns (success, message).
        """
        if self._game_active:
            return False, "A game is already in progress!"

        # Bypass cooldown for manual trigger
        success = await self._start_game(manual=True)
        if success:
            return True, "City guessing game started!"
        return False, "Failed to start game (check if city images exist in assets/cities/)"


# =============================================================================
# Admin Command
# =============================================================================

class CityGameCog(commands.Cog):
    """Admin commands for city game."""

    def __init__(self, bot: "SyriaBot") -> None:
        self.bot = bot

    @app_commands.command(name="deadchat", description="Manually start a governorate guessing game (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def deadchat(self, interaction: discord.Interaction) -> None:
        """Manually trigger a governorate guessing game."""
        if not self.bot.city_game_service:
            await interaction.response.send_message(
                "City game service is not running.",
                ephemeral=True
            )
            return

        success, message = await self.bot.city_game_service.manual_start()
        await interaction.response.send_message(message, ephemeral=True)


# Singleton
city_game_service: Optional[CityGameService] = None


def get_city_game_service(bot: "SyriaBot" = None) -> Optional[CityGameService]:
    """Get or create the city game service singleton."""
    global city_game_service
    if city_game_service is None and bot is not None:
        city_game_service = CityGameService(bot)
    return city_game_service


async def setup_city_game_cog(bot: "SyriaBot") -> None:
    """Add the city game admin command cog."""
    await bot.add_cog(CityGameCog(bot))
    log.tree("City Game Cog Loaded", [
        ("Command", "/deadchat"),
    ], emoji="🏙️")
