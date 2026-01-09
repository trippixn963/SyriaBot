"""
SyriaBot - Configuration
========================

Central configuration from environment variables.
All env vars prefixed with SYRIA_ for namespacing.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet


ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = ROOT_DIR / "logs"

DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)


def _env(key: str, default: str = "") -> str:
    """Get environment variable with default."""
    return os.getenv(key, default)


def _env_int(key: str, default: int = 0) -> int:
    """Get environment variable as int with default."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(key: str, default: float = 0.0) -> float:
    """Get environment variable as float with default."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_set(key: str) -> FrozenSet[int]:
    """Get environment variable as set of ints (comma-separated)."""
    value = os.getenv(key, "")
    if not value:
        return frozenset()
    try:
        return frozenset(int(x.strip()) for x in value.split(",") if x.strip())
    except ValueError:
        return frozenset()


def _env_map(key: str) -> Dict[int, int]:
    """Get environment variable as int:int mapping (e.g., '5:123,10:456')."""
    value = os.getenv(key, "")
    if not value:
        return {}
    result = {}
    try:
        for pair in value.split(","):
            if ":" in pair:
                k, v = pair.strip().split(":")
                result[int(k)] = int(v)
        return result
    except ValueError:
        return {}


@dataclass(frozen=True)
class Config:
    """Bot configuration from environment variables."""

    # ==========================================================================
    # Core
    # ==========================================================================
    TOKEN: str = _env("SYRIA_TOKEN")
    GUILD_ID: int = _env_int("SYRIA_GUILD")
    OWNER_ID: int = _env_int("SYRIA_OWNER")

    # ==========================================================================
    # Roles
    # ==========================================================================
    MOD_ROLE_ID: int = _env_int("SYRIA_MOD_ROLE")
    AUTO_ROLE_ID: int = _env_int("SYRIA_AUTO_ROLE")
    BOOSTER_ROLE_ID: int = _env_int("SYRIA_BOOSTER_ROLE")

    # ==========================================================================
    # Channels
    # ==========================================================================
    GENERAL_CHANNEL_ID: int = _env_int("SYRIA_GENERAL_CH")
    GALLERY_CHANNEL_ID: int = _env_int("SYRIA_GALLERY_CH")
    MEMES_CHANNEL_ID: int = _env_int("SYRIA_MEMES_CH")
    BUMP_CHANNEL_ID: int = _env_int("SYRIA_BUMP_CH")
    FUN_COMMANDS_CHANNEL_ID: int = _env_int("SYRIA_FUN_CH")

    # ==========================================================================
    # TempVoice
    # ==========================================================================
    VC_CREATOR_CHANNEL_ID: int = _env_int("SYRIA_VC_CREATOR")
    VC_CATEGORY_ID: int = _env_int("SYRIA_VC_CATEGORY")
    VC_INTERFACE_CHANNEL_ID: int = _env_int("SYRIA_VC_INTERFACE")
    VC_CLEANUP_INTERVAL: int = _env_int("SYRIA_VC_CLEANUP", 300)
    VC_PROTECTED_CHANNELS: FrozenSet[int] = field(
        default_factory=lambda: _env_set("SYRIA_VC_PROTECTED")
    )
    VC_IGNORED_CHANNELS: FrozenSet[int] = field(
        default_factory=lambda: _env_set("SYRIA_VC_IGNORED")
    )

    # ==========================================================================
    # XP System
    # ==========================================================================
    XP_MESSAGE_MIN: int = _env_int("SYRIA_XP_MIN", 8)
    XP_MESSAGE_MAX: int = _env_int("SYRIA_XP_MAX", 12)
    XP_VOICE_PER_MIN: int = _env_int("SYRIA_XP_VOICE", 3)
    XP_MESSAGE_COOLDOWN: int = _env_int("SYRIA_XP_COOLDOWN", 60)
    XP_BOOSTER_MULTIPLIER: float = _env_float("SYRIA_XP_BOOST", 2.0)
    XP_IGNORED_CHANNELS: FrozenSet[int] = field(
        default_factory=lambda: _env_set("SYRIA_XP_IGNORED")
    )
    XP_ROLE_REWARDS: Dict[int, int] = field(
        default_factory=lambda: _env_map("SYRIA_XP_ROLES")
    )
    XP_API_KEY: str = _env("SYRIA_XP_API_KEY")

    # ==========================================================================
    # Confessions
    # ==========================================================================
    CONFESSIONS_CHANNEL_ID: int = _env_int("SYRIA_CONFESS_CH")
    CONFESSIONS_MOD_CHANNEL_ID: int = _env_int("SYRIA_CONFESS_MOD_CH")

    # ==========================================================================
    # Rate Limits
    # ==========================================================================
    DOWNLOAD_WEEKLY_LIMIT: int = _env_int("SYRIA_DOWNLOAD_LIMIT", 5)
    IMAGE_WEEKLY_LIMIT: int = _env_int("SYRIA_IMAGE_LIMIT", 5)

    # ==========================================================================
    # External APIs
    # ==========================================================================
    OPENWEATHER_API_KEY: str = _env("OPENWEATHER_API_KEY")
    OPENAI_API_KEY: str = _env("OPENAI_API_KEY")
    GOOGLE_API_KEY: str = _env("GOOGLE_API_KEY")
    GOOGLE_CX: str = _env("GOOGLE_CX")
    DEEPL_API_KEY: str = _env("DEEPL_API_KEY")

    # ==========================================================================
    # Webhooks
    # ==========================================================================
    STATUS_WEBHOOK_URL: str = _env("SYRIA_STATUS_WEBHOOK")

    # ==========================================================================
    # URLs
    # ==========================================================================
    LEADERBOARD_BASE_URL: str = _env("SYRIA_LEADERBOARD_URL", "https://trippixn.com/syria/leaderboard")

    # ==========================================================================
    # Paths (computed)
    # ==========================================================================
    DATABASE_PATH: str = str(DATA_DIR / "syria.db")


config = Config()
