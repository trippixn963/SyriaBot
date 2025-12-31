"""
SyriaBot - Configuration
========================

Central configuration from environment variables.

Author: حَـــــنَّـــــا
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet


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

    # Cleanup settings
    VC_CLEANUP_INTERVAL: int = _get_env_int("SYRIA_VC_CLEANUP_INTERVAL", 300)  # 5 minutes

    # Roles
    MOD_ROLE_ID: int = _get_env_int("SYRIA_MOD_ROLE_ID", 0)

    # Database
    DATABASE_PATH: str = str(DATA_DIR / "syria.db")


config = Config()
