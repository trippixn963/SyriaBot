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


def _env_required(key: str) -> str:
    """Get required environment variable. Raises if not set."""
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Required environment variable {key} is not set")
    return value


def _env_int_required(key: str) -> int:
    """Get required environment variable as int. Raises if not set."""
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Required environment variable {key} is not set")
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable {key} must be an integer, got: {value}")


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
    GUILD_ID: int = _env_int("GUILD_ID")
    OWNER_ID: int = _env_int("OWNER_ID")

    # ==========================================================================
    # Roles
    # ==========================================================================
    MOD_ROLE_ID: int = _env_int("MOD_ROLE_ID")
    AUTO_ROLE_ID: int = _env_int("SYRIA_AUTO_ROLE")
    BOOSTER_ROLE_ID: int = _env_int("BOOSTER_ROLE_ID")

    # ==========================================================================
    # Channels
    # ==========================================================================
    GENERAL_CHANNEL_ID: int = _env_int("GENERAL_CHANNEL_ID")
    RULES_CHANNEL_ID: int = _env_int("SYRIA_RULES_CH")
    GALLERY_CHANNEL_ID: int = _env_int("SYRIA_GALLERY_CH")
    MEMES_CHANNEL_ID: int = _env_int("SYRIA_MEMES_CH")
    BUMP_CHANNEL_ID: int = _env_int("SYRIA_BUMP_CH")
    CMDS_CHANNEL_ID: int = _env_int("SYRIA_CMDS_CH")
    INBOX_CHANNEL_ID: int = _env_int("SYRIA_INBOX_CH")
    GIVEAWAY_CHANNEL_ID: int = _env_int("SYRIA_GIVEAWAY_CH")
    TICKET_CHANNEL_ID: int = _env_int("SYRIA_TICKET_CH")
    ROLE_SHOP_CHANNEL_ID: int = _env_int("SYRIA_ROLE_SHOP_CH")
    FLAGS_GAME_CHANNEL_ID: int = _env_int("SYRIA_FLAGS_CH")
    COUNTING_CHANNEL_ID: int = _env_int("SYRIA_COUNTING_CH")

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
    VC_MOD_ROLES: FrozenSet[int] = field(
        default_factory=lambda: _env_set("SYRIA_VC_MOD_ROLES")
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

    # ==========================================================================
    # Confessions
    # ==========================================================================
    CONFESSIONS_CHANNEL_ID: int = _env_int("SYRIA_CONFESS_CH")

    # ==========================================================================
    # Asset Storage (for permanent GIF URLs)
    # ==========================================================================
    ASSET_STORAGE_CHANNEL_ID: int = _env_int("SYRIA_ASSET_CH")

    # ==========================================================================
    # Rate Limits
    # ==========================================================================
    DOWNLOAD_WEEKLY_LIMIT: int = _env_int("SYRIA_DOWNLOAD_LIMIT", 5)
    IMAGE_WEEKLY_LIMIT: int = _env_int("SYRIA_IMAGE_LIMIT", 5)

    # ==========================================================================
    # Birthdays
    # ==========================================================================
    BIRTHDAY_ROLE_ID: int = _env_int("SYRIA_BIRTHDAY_ROLE")
    BIRTHDAY_ANNOUNCE_CHANNEL_ID: int = _env_int("SYRIA_BIRTHDAY_CH")

    # ==========================================================================
    # External APIs
    # ==========================================================================
    OPENWEATHER_API_KEY: str = _env("OPENWEATHER_API_KEY")
    OPENAI_API_KEY: str = _env("OPENAI_API_KEY")
    GOOGLE_API_KEY: str = _env("GOOGLE_API_KEY")
    GOOGLE_CX: str = _env("GOOGLE_CX")
    DEEPL_API_KEY: str = _env("DEEPL_API_KEY")

    # ==========================================================================
    # JawdatBot Integration (Casino Currency) - no defaults, must configure
    # ==========================================================================
    JAWDAT_API_URL: str = _env("JAWDAT_API_URL")
    JAWDAT_API_KEY: str = _env("JAWDAT_API_KEY")

    # ==========================================================================
    # Social Media Monitor
    # ==========================================================================
    SOCIAL_MONITOR_CH: int = _env_int("SYRIA_SOCIAL_CH")
    TIKTOK_USERNAME: str = _env("SYRIA_TIKTOK_USER")
    INSTAGRAM_USERNAME: str = _env("SYRIA_INSTAGRAM_USER")

    # ==========================================================================
    # URLs
    # ==========================================================================
    LEADERBOARD_BASE_URL: str = _env("SYRIA_LEADERBOARD_URL", "https://trippixn.com/syria/leaderboard")

    # ==========================================================================
    # Giveaway
    # ==========================================================================
    GIVEAWAY_JOIN_EMOJI_ID: int = _env_int("SYRIA_GIVEAWAY_EMOJI")
    GIVEAWAY_REQUIRED_LEVEL: int = _env_int("SYRIA_GIVEAWAY_LEVEL", 10)

    # ==========================================================================
    # Fun Commands (Ship special override)
    # ==========================================================================
    SHIP_SPECIAL_USER_ID: int = _env_int("SYRIA_SHIP_SPECIAL_USER")

    # ==========================================================================
    # FAQ Ignored Channels
    # ==========================================================================
    FAQ_IGNORED_CHANNELS: FrozenSet[int] = field(
        default_factory=lambda: _env_set("SYRIA_FAQ_IGNORED")
    )

    # ==========================================================================
    # Paths (computed)
    # ==========================================================================
    DATABASE_PATH: str = str(DATA_DIR / "syria.db")


config = Config()


def validate_config() -> bool:
    """
    Validate configuration at startup.

    Logs warnings for missing optional configs and errors for critical issues.

    Returns:
        True if critical config is valid, False if bot cannot start
    """
    from src.core.logger import logger

    is_valid = True
    warnings = []
    errors = []

    # Critical: Token must be set
    if not config.TOKEN:
        errors.append(("SYRIA_TOKEN", "Bot token is required"))
        is_valid = False

    # Critical: Guild ID should be set
    if not config.GUILD_ID:
        errors.append(("GUILD_ID", "Main guild ID is required"))
        is_valid = False

    # Important but not critical
    if not config.MOD_ROLE_ID:
        warnings.append(("MOD_ROLE_ID", "Moderation features limited"))
    if not config.BOOSTER_ROLE_ID:
        warnings.append(("SYRIA_BOOSTER_ROLE", "Booster XP multiplier disabled"))

    # TempVoice config
    if config.VC_CREATOR_CHANNEL_ID and not config.VC_CATEGORY_ID:
        warnings.append(("SYRIA_VC_CATEGORY", "TempVoice may not work properly"))

    # XP System
    if not config.XP_ROLE_REWARDS:
        warnings.append(("SYRIA_XP_ROLES", "XP level role rewards disabled"))

    # External APIs (info level - expected to be optional)
    optional_apis = []
    if not config.OPENWEATHER_API_KEY:
        optional_apis.append("Weather")
    if not config.OPENAI_API_KEY:
        optional_apis.append("AI")
    if not config.DEEPL_API_KEY:
        optional_apis.append("Translation")
    if not config.GOOGLE_API_KEY or not config.GOOGLE_CX:
        optional_apis.append("ImageSearch")

    # Log results
    if errors:
        for key, reason in errors:
            logger.tree("Config Error", [
                ("Variable", key),
                ("Reason", reason),
                ("Impact", "Bot cannot start"),
            ], emoji="🚨")

    if warnings:
        for key, reason in warnings:
            logger.tree("Config Warning", [
                ("Variable", key),
                ("Reason", reason),
            ], emoji="⚠️")

    if optional_apis:
        logger.tree("Optional APIs Not Configured", [
            ("APIs", ", ".join(optional_apis)),
            ("Impact", "Related commands disabled"),
        ], emoji="ℹ️")

    if is_valid and not warnings:
        logger.tree("Config Validation", [
            ("Status", "All checks passed"),
        ], emoji="✅")
    elif is_valid:
        logger.tree("Config Validation", [
            ("Status", "Passed with warnings"),
            ("Warnings", str(len(warnings))),
        ], emoji="⚠️")

    return is_valid
