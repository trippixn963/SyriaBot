"""
SyriaBot - City Guessing Game
=============================

Dead chat reviver that shows Syrian city images for users to guess.

Features:
- Triggers after 30 min of chat inactivity
- Fetches city images from Wikipedia
- First correct guess wins 1k XP
- 10 minute time limit per game

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import random
import time
from typing import TYPE_CHECKING, Optional, Dict, List, Set
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord.ext import tasks

from src.core.config import config
from src.core.colors import COLOR_SYRIA_GREEN
from src.core.logger import log
from src.utils.footer import set_footer

if TYPE_CHECKING:
    from src.bot import SyriaBot


# =============================================================================
# Configuration
# =============================================================================

DEAD_CHAT_ROLE_ID = 1301584721251405896
GENERAL_CHANNEL_ID = 1350540215797940245
INACTIVITY_THRESHOLD = 30 * 60  # 30 minutes in seconds
GUESS_TIME_LIMIT = 10 * 60  # 10 minutes in seconds
XP_REWARD = 1000
GAME_COOLDOWN = 60 * 60  # 1 hour cooldown between games


# =============================================================================
# Syrian Cities Data
# =============================================================================

SYRIAN_CITIES = [
    {
        "english": "Damascus",
        "arabic": "دمشق",
        "aliases": ["dimashq", "sham", "الشام"],
        "wiki": "Damascus",
    },
    {
        "english": "Aleppo",
        "arabic": "حلب",
        "aliases": ["halab"],
        "wiki": "Aleppo",
    },
    {
        "english": "Homs",
        "arabic": "حمص",
        "aliases": ["hims"],
        "wiki": "Homs",
    },
    {
        "english": "Latakia",
        "arabic": "اللاذقية",
        "aliases": ["lattakia", "al-ladhiqiyah", "اللازقية"],
        "wiki": "Latakia",
    },
    {
        "english": "Hama",
        "arabic": "حماة",
        "aliases": ["hamah", "حماه"],
        "wiki": "Hama",
    },
    {
        "english": "Tartus",
        "arabic": "طرطوس",
        "aliases": ["tartous", "tartous"],
        "wiki": "Tartus",
    },
    {
        "english": "Deir ez-Zor",
        "arabic": "دير الزور",
        "aliases": ["deir ezzor", "deir al-zor", "دير ازور"],
        "wiki": "Deir_ez-Zor",
    },
    {
        "english": "Raqqa",
        "arabic": "الرقة",
        "aliases": ["ar-raqqah", "rakka", "الرقه"],
        "wiki": "Raqqa",
    },
    {
        "english": "Idlib",
        "arabic": "إدلب",
        "aliases": ["adlib", "ادلب"],
        "wiki": "Idlib",
    },
    {
        "english": "Daraa",
        "arabic": "درعا",
        "aliases": ["deraa", "dar'a"],
        "wiki": "Daraa",
    },
    {
        "english": "Qamishli",
        "arabic": "القامشلي",
        "aliases": ["qamishlo", "kamishli", "القامشلى"],
        "wiki": "Qamishli",
    },
    {
        "english": "Palmyra",
        "arabic": "تدمر",
        "aliases": ["tadmor", "tadmur"],
        "wiki": "Palmyra",
    },
    {
        "english": "Bosra",
        "arabic": "بصرى",
        "aliases": ["busra", "bosra al-sham"],
        "wiki": "Bosra",
    },
    {
        "english": "Sweida",
        "arabic": "السويداء",
        "aliases": ["suwayda", "as-suwayda", "السويدا"],
        "wiki": "As-Suwayda",
    },
    {
        "english": "Masyaf",
        "arabic": "مصياف",
        "aliases": ["masyaf castle", "مصيف"],
        "wiki": "Masyaf",
    },
    {
        "english": "Safita",
        "arabic": "صافيتا",
        "aliases": ["chastel blanc"],
        "wiki": "Safita",
    },
    {
        "english": "Maaloula",
        "arabic": "معلولا",
        "aliases": ["maalula", "ma'loula"],
        "wiki": "Maaloula",
    },
    {
        "english": "Apamea",
        "arabic": "أفاميا",
        "aliases": ["afamia", "apameia"],
        "wiki": "Apamea,_Syria",
    },
    {
        "english": "Krak des Chevaliers",
        "arabic": "قلعة الحصن",
        "aliases": ["krak", "qalaat al-hosn", "حصن الاكراد", "قلعه الحصن"],
        "wiki": "Krak_des_Chevaliers",
    },
    {
        "english": "Ugarit",
        "arabic": "أوغاريت",
        "aliases": ["ras shamra", "رأس شمرا"],
        "wiki": "Ugarit",
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
        self._session: Optional[aiohttp.ClientSession] = None
        self._recently_used: List[str] = []  # Track recently used cities

    async def setup(self) -> None:
        """Initialize the city game service."""
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        self._last_message_time = time.time()

        # Start the inactivity checker
        self.inactivity_check.start()

        log.tree("City Game Service Ready", [
            ("Channel", str(GENERAL_CHANNEL_ID)),
            ("Role", str(DEAD_CHAT_ROLE_ID)),
            ("Inactivity", f"{INACTIVITY_THRESHOLD // 60} min"),
            ("Time Limit", f"{GUESS_TIME_LIMIT // 60} min"),
            ("Reward", f"{XP_REWARD:,} XP"),
            ("Cities", str(len(SYRIAN_CITIES))),
        ], emoji="🏙️")

    def stop(self) -> None:
        """Stop the city game service."""
        if self.inactivity_check.is_running():
            self.inactivity_check.cancel()
        log.tree("City Game Service Stopped", [], emoji="🛑")

    async def close(self) -> None:
        """Clean up resources."""
        self.stop()
        if self._session:
            await self._session.close()
            self._session = None

    def on_message(self, channel_id: int) -> None:
        """Update last message time when a message is sent in the tracked channel."""
        if channel_id == GENERAL_CHANNEL_ID:
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

    async def _get_city_image(self, wiki_title: str) -> Optional[str]:
        """Fetch the main image URL for a Wikipedia article."""
        if not self._session:
            return None

        try:
            # Use Wikipedia API to get page image
            url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + wiki_title

            async with self._session.get(url) as resp:
                if resp.status != 200:
                    log.tree("Wiki Image Fetch Failed", [
                        ("City", wiki_title),
                        ("Status", str(resp.status)),
                    ], emoji="⚠️")
                    return None

                data = await resp.json()

                # Get the original image URL
                if "originalimage" in data:
                    return data["originalimage"]["source"]
                elif "thumbnail" in data:
                    return data["thumbnail"]["source"]

                return None

        except Exception as e:
            log.tree("Wiki Image Error", [
                ("City", wiki_title),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return None

    def _get_random_city(self) -> Dict:
        """Get a random city that hasn't been used recently."""
        available = [c for c in SYRIAN_CITIES if c["english"] not in self._recently_used]

        if not available:
            # Reset if all cities used
            self._recently_used = []
            available = SYRIAN_CITIES

        city = random.choice(available)
        self._recently_used.append(city["english"])

        # Keep only last 10 in recent list
        if len(self._recently_used) > 10:
            self._recently_used = self._recently_used[-10:]

        return city

    async def _start_game(self) -> None:
        """Start a new city guessing game."""
        channel = self.bot.get_channel(GENERAL_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            log.tree("City Game Channel Not Found", [
                ("Channel ID", str(GENERAL_CHANNEL_ID)),
            ], emoji="⚠️")
            return

        # Select a city
        city = self._get_random_city()

        # Get image
        image_url = await self._get_city_image(city["wiki"])
        if not image_url:
            log.tree("City Game Skipped", [
                ("City", city["english"]),
                ("Reason", "No image found"),
            ], emoji="⚠️")
            return

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
        embed.set_image(url=image_url)
        set_footer(embed)

        try:
            self._game_message = await channel.send(
                content=f"<@&{DEAD_CHAT_ROLE_ID}>",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True)
            )

            log.tree("City Game Started", [
                ("City", city["english"]),
                ("Arabic", city["arabic"]),
                ("Channel", channel.name),
            ], emoji="🏙️")

            # Start timeout task
            asyncio.create_task(self._game_timeout())

        except Exception as e:
            self._game_active = False
            self._current_city = None
            log.error_tree("City Game Start Failed", e)

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

        if message.channel.id != GENERAL_CHANNEL_ID:
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
        channel = self.bot.get_channel(GENERAL_CHANNEL_ID)

        self._game_active = False
        self._last_game_time = time.time()

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


# Singleton
city_game_service: Optional[CityGameService] = None


def get_city_game_service(bot: "SyriaBot" = None) -> Optional[CityGameService]:
    """Get or create the city game service singleton."""
    global city_game_service
    if city_game_service is None and bot is not None:
        city_game_service = CityGameService(bot)
    return city_game_service
