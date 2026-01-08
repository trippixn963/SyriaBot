"""
SyriaBot - Configuration
========================

Central configuration from environment variables.

Author: حَـــــنَّـــــا
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


def _get_env_int(key: str, default: int) -> int:
    """Get environment variable as int with default."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_int_set(key: str, default: str = "") -> FrozenSet[int]:
    """Get environment variable as a set of ints (comma-separated)."""
    value = os.getenv(key, default)
    if not value:
        return frozenset()
    try:
        return frozenset(int(x.strip()) for x in value.split(",") if x.strip())
    except ValueError:
        return frozenset()


def _get_env_role_rewards(key: str) -> Dict[int, int]:
    """Get environment variable as level:role_id mapping.

    Format: "5:123456,10:789012,20:345678"
    Returns: {5: 123456, 10: 789012, 20: 345678}
    """
    value = os.getenv(key, "")
    if not value:
        return {}
    rewards = {}
    try:
        for pair in value.split(","):
            if ":" in pair:
                level, role_id = pair.strip().split(":")
                rewards[int(level)] = int(role_id)
        return rewards
    except ValueError:
        return {}


@dataclass(frozen=True)
class Config:
    """Bot configuration from environment variables."""

    # Bot settings
    TOKEN: str = os.getenv("SYRIA_BOT_TOKEN", "")
    GUILD_ID: int = _get_env_int("SYRIA_GUILD_ID", 0)
    OWNER_ID: int = _get_env_int("SYRIA_OWNER_ID", 0)

    # Voice settings
    VC_CREATOR_CHANNEL_ID: int = _get_env_int("SYRIA_VC_CREATOR_ID", 0)
    VC_CATEGORY_ID: int = _get_env_int("SYRIA_VC_CATEGORY_ID", 0)
    VC_INTERFACE_CHANNEL_ID: int = _get_env_int("SYRIA_VC_INTERFACE_ID", 0)

    # Protected channels (never auto-deleted) - comma-separated IDs
    VC_PROTECTED_CHANNELS: FrozenSet[int] = field(
        default_factory=lambda: _get_env_int_set("SYRIA_VC_PROTECTED_IDS", "")
    )

    # Ignored channels (no permission changes, no voice XP) - comma-separated IDs
    # Use for channels managed by other bots (e.g., Quran VC)
    VC_IGNORED_CHANNELS: FrozenSet[int] = field(
        default_factory=lambda: _get_env_int_set("SYRIA_VC_IGNORED_IDS", "")
    )

    # Cleanup settings
    VC_CLEANUP_INTERVAL: int = _get_env_int("SYRIA_VC_CLEANUP_INTERVAL", 300)  # 5 minutes

    # Roles
    MOD_ROLE_ID: int = _get_env_int("SYRIA_MOD_ROLE_ID", 0)
    AUTO_ROLE_ID: int = _get_env_int("SYRIA_AUTO_ROLE_ID", 0)
    BOOSTER_ROLE_ID: int = _get_env_int("SYRIA_BOOSTER_ROLE_ID", 0)

    # Channels
    GENERAL_CHANNEL_ID: int = _get_env_int("SYRIA_GENERAL_CHANNEL_ID", 0)

    # APIs
    OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Google Custom Search API (for /image command)
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_CX: str = os.getenv("GOOGLE_CX", "")

    # DeepL API (for translation)
    DEEPL_API_KEY: str = os.getenv("DEEPL_API_KEY", "")

    # Webhooks (read directly by logger from env vars)
    # SYRIA_LIVE_LOGS_WEBHOOK_URL - Tree format console logs streaming
    # SYRIA_ERROR_WEBHOOK_URL - Error-only logs
    STATUS_WEBHOOK_URL: str = os.getenv("SYRIA_STATUS_WEBHOOK_URL", "")

    # Database
    DATABASE_PATH: str = str(DATA_DIR / "syria.db")

    # XP System
    XP_MESSAGE_MIN: int = _get_env_int("SYRIA_XP_MESSAGE_MIN", 15)
    XP_MESSAGE_MAX: int = _get_env_int("SYRIA_XP_MESSAGE_MAX", 25)
    XP_VOICE_PER_MIN: int = _get_env_int("SYRIA_XP_VOICE_PER_MIN", 5)
    XP_MESSAGE_COOLDOWN: int = _get_env_int("SYRIA_XP_MESSAGE_COOLDOWN", 60)
    XP_BOOSTER_MULTIPLIER: float = float(os.getenv("SYRIA_XP_BOOSTER_MULTIPLIER", "2.0"))

    # XP Ignored Channels - no message XP (e.g., prison)
    XP_IGNORED_CHANNELS: FrozenSet[int] = field(
        default_factory=lambda: _get_env_int_set("SYRIA_XP_IGNORED_CHANNELS", "")
    )

    # XP Role Rewards (level:role_id pairs)
    XP_ROLE_REWARDS: Dict[int, int] = field(
        default_factory=lambda: _get_env_role_rewards("SYRIA_XP_ROLE_REWARDS")
    )

    # Download System
    DOWNLOAD_WEEKLY_LIMIT: int = _get_env_int("SYRIA_DOWNLOAD_WEEKLY_LIMIT", 5)

    # Image Search System
    IMAGE_WEEKLY_LIMIT: int = _get_env_int("SYRIA_IMAGE_WEEKLY_LIMIT", 5)

    # Gallery Channel (media-only)
    GALLERY_CHANNEL_ID: int = _get_env_int("SYRIA_GALLERY_CHANNEL_ID", 1408234733988483212)
    MEMES_CHANNEL_ID: int = _get_env_int("SYRIA_MEMES_CHANNEL_ID", 1442153997610913812)
    GALLERY_HEART_EMOJI: str = "<:heart:1456779669805203539>"

    # Bump Reminder (Disboard)
    BUMP_CHANNEL_ID: int = _get_env_int("SYRIA_BUMP_CHANNEL_ID", 0)
    BUMP_ROLE_ID: int = _get_env_int("SYRIA_BUMP_ROLE_ID", 0)


config = Config()
