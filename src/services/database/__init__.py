"""
SyriaBot - Database Module
==========================

Modular SQLite database for all bot features.

Structure:
    - core.py: Base class with connection management and table init
    - tempvoice.py: TempVoice channel operations
    - rate_limits.py: Weekly usage tracking
    - xp.py: XP/Leveling system
    - stats.py: Server-level statistics
    - afk.py: AFK system
    - downloads.py: Download statistics

Author: حَـــــنَّـــــا
"""

from .core import DatabaseCore
from .tempvoice import TempVoiceMixin
from .rate_limits import RateLimitsMixin
from .xp import XPMixin
from .stats import StatsMixin
from .afk import AFKMixin
from .downloads import DownloadsMixin


class Database(
    TempVoiceMixin,
    RateLimitsMixin,
    XPMixin,
    StatsMixin,
    AFKMixin,
    DownloadsMixin,
    DatabaseCore,
):
    """
    Complete database class combining all mixins.

    Inherits from all feature mixins and the core database class.
    The order matters - DatabaseCore must be last so its __init__ runs.
    """
    pass


# Global singleton instance
db = Database()

# Re-export for backwards compatibility
__all__ = ["Database", "db"]
