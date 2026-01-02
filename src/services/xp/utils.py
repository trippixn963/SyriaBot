"""
XP System - Utility Functions
=============================

Level calculations and XP formulas.
"""

from typing import Tuple

from src.core.constants import XP_BASE_MULTIPLIER


def xp_for_level(level: int) -> int:
    """
    Calculate total XP needed to reach a level.

    Formula: XP_BASE_MULTIPLIER * level^1.5

    Examples:
        Level 1:   100 XP
        Level 10:  3,162 XP
        Level 50:  35,355 XP
        Level 100: 100,000 XP
    """
    if level <= 0:
        return 0
    return int(XP_BASE_MULTIPLIER * (level ** 1.5))


def level_from_xp(xp: int) -> int:
    """
    Calculate level from total XP.

    Inverse of xp_for_level: level = (xp / XP_BASE_MULTIPLIER)^(2/3)
    """
    if xp <= 0:
        return 0
    return int((xp / XP_BASE_MULTIPLIER) ** (2 / 3))


def xp_progress(xp: int) -> Tuple[int, int, int, float]:
    """
    Get detailed XP progress information.

    Returns:
        Tuple of (current_level, xp_into_level, xp_needed_for_next, progress_percent)
    """
    current_level = level_from_xp(xp)
    current_level_xp = xp_for_level(current_level)
    next_level_xp = xp_for_level(current_level + 1)

    xp_into_level = xp - current_level_xp
    xp_needed = next_level_xp - current_level_xp

    if xp_needed <= 0:
        progress = 1.0
    else:
        progress = xp_into_level / xp_needed

    return current_level, xp_into_level, xp_needed, min(1.0, max(0.0, progress))


def format_xp(xp: int) -> str:
    """Format XP with comma separators."""
    return f"{xp:,}"


def progress_bar(progress: float, length: int = 10) -> str:
    """
    Create a text progress bar.

    Args:
        progress: Float between 0.0 and 1.0
        length: Number of characters in the bar

    Returns:
        String like "████████░░" for 80% progress
    """
    filled = int(progress * length)
    empty = length - filled
    return "█" * filled + "░" * empty


def format_voice_time(minutes: int) -> str:
    """Format voice minutes as human-readable string."""
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    mins = minutes % 60
    if hours < 24:
        return f"{hours}h {mins}m" if mins else f"{hours}h"
    days = hours // 24
    hours = hours % 24
    if hours:
        return f"{days}d {hours}h"
    return f"{days}d"
