"""
SyriaBot - Database Backup Service
==================================

Automated SQLite database backup with daily rotation and retention policy.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from src.core.logger import logger


# =============================================================================
# Constants
# =============================================================================

DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_RETENTION_DAYS = 7
DEFAULT_BACKUP_HOUR = 0  # Midnight

KB_DIVISOR = 1024
SECONDS_PER_HOUR = 3600

# SyriaBot-Specific Configuration
DATABASE_PATH = Path("data/syria.db")
BACKUP_DIR = Path("data/backups")
BACKUP_PREFIX = "syria"


# =============================================================================
# Timezone Helper
# =============================================================================

def _get_timezone(timezone_name: Optional[str] = None) -> ZoneInfo:
    """Get timezone, with fallback to default."""
    try:
        return ZoneInfo(timezone_name or DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


# =============================================================================
# Backup Functions Factory
# =============================================================================

def create_backup_system(
    database_path: str = "data/syria.db",
    backup_prefix: str = "syria",
    backup_dir: str = "data/backups",
    retention_days: int = DEFAULT_RETENTION_DAYS,
    backup_hour: int = DEFAULT_BACKUP_HOUR,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> Dict[str, any]:
    """
    Create a backup system with configuration.

    Args:
        database_path: Path to the SQLite database file
        backup_prefix: Prefix for backup filenames
        backup_dir: Directory to store backups
        retention_days: Number of days to retain backups
        backup_hour: Hour to run daily backups (0-23)
        timezone_name: Timezone name for timestamps

    Returns:
        Dict containing backup functions and configuration
    """
    db_path = Path(database_path)
    bak_dir = Path(backup_dir)
    tz = _get_timezone(timezone_name)

    def create_backup() -> Optional[Path]:
        """Create a backup of the SQLite database."""
        if not db_path.exists():
            logger.warning("Database Backup Skipped", [
                ("Reason", "Database file does not exist"),
                ("Path", str(db_path)),
            ])
            return None

        bak_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(tz).strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"{backup_prefix}_{timestamp}.db"
        backup_path = bak_dir / backup_filename

        try:
            shutil.copy2(db_path, backup_path)
            backup_size = backup_path.stat().st_size

            logger.tree("Database Backup Created", [
                ("Backup", backup_filename),
                ("Size", f"{backup_size / KB_DIVISOR:.1f} KB"),
                ("Location", str(bak_dir)),
            ], emoji="💾")

            return backup_path

        except Exception as e:
            logger.error("Database Backup Failed", [
                ("Error", str(e)),
                ("Path", str(db_path)),
            ])
            return None

    def cleanup_old_backups() -> int:
        """Remove backups older than retention_days."""
        if not bak_dir.exists():
            return 0

        cutoff_date = datetime.now(tz) - timedelta(days=retention_days)
        removed_count = 0

        for backup_file in bak_dir.glob(f"{backup_prefix}_*.db"):
            try:
                filename = backup_file.stem
                parts = filename.split("_")

                if len(parts) < 2 or parts[0] != backup_prefix:
                    continue

                date_str = parts[1]

                if len(date_str) != 10 or date_str.count("-") != 2:
                    continue

                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                file_date = file_date.replace(tzinfo=tz)

                if file_date < cutoff_date:
                    backup_file.unlink()
                    removed_count += 1

            except (ValueError, OSError) as e:
                logger.tree("Backup Parse Error", [
                    ("File", backup_file.name),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
                continue

        if removed_count > 0:
            logger.info("Old Backups Cleaned Up", [
                ("Removed", str(removed_count)),
                ("Retention", f"{retention_days} days"),
            ])

        return removed_count

    def list_backups() -> List[Dict]:
        """List all available backups with their metadata."""
        if not bak_dir.exists():
            return []

        backups = []
        for backup_file in sorted(bak_dir.glob(f"{backup_prefix}_*.db"), reverse=True):
            try:
                stat = backup_file.stat()
                backups.append({
                    "path": backup_file,
                    "name": backup_file.name,
                    "size_kb": stat.st_size / KB_DIVISOR,
                    "created": datetime.fromtimestamp(stat.st_mtime, tz=tz),
                })
            except OSError:
                continue

        return backups

    def get_latest_backup() -> Optional[Path]:
        """Get the most recent backup file."""
        backups = list_backups()
        return backups[0]["path"] if backups else None

    def has_backup_today() -> bool:
        """Check if a backup already exists for today."""
        if not bak_dir.exists():
            return False

        today = datetime.now(tz).strftime("%Y-%m-%d")
        for _ in bak_dir.glob(f"{backup_prefix}_{today}_*.db"):
            return True
        return False

    def seconds_until_next_backup() -> float:
        """Calculate seconds until next scheduled backup time."""
        now = datetime.now(tz)
        target = now.replace(hour=backup_hour, minute=0, second=0, microsecond=0)

        if now >= target:
            target += timedelta(days=1)

        return (target - now).total_seconds()

    return {
        "create_backup": create_backup,
        "cleanup_old_backups": cleanup_old_backups,
        "list_backups": list_backups,
        "get_latest_backup": get_latest_backup,
        "has_backup_today": has_backup_today,
        "seconds_until_next_backup": seconds_until_next_backup,
        "database_path": db_path,
        "backup_dir": bak_dir,
        "backup_prefix": backup_prefix,
        "retention_days": retention_days,
        "backup_hour": backup_hour,
        "timezone": tz,
    }


# =============================================================================
# Backup Scheduler
# =============================================================================

class BackupScheduler:
    """
    Schedules daily database backups at a specific time.

    DESIGN: Runs backup at configured hour daily (default midnight).
    Also cleans up old backups after each backup.
    """

    def __init__(
        self,
        database_path: str = str(DATABASE_PATH),
        backup_prefix: str = BACKUP_PREFIX,
        backup_dir: str = str(BACKUP_DIR),
        retention_days: int = DEFAULT_RETENTION_DAYS,
        backup_hour: int = DEFAULT_BACKUP_HOUR,
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> None:
        """Initialize the backup scheduler."""
        self._system = create_backup_system(
            database_path=database_path,
            backup_prefix=backup_prefix,
            backup_dir=backup_dir,
            retention_days=retention_days,
            backup_hour=backup_hour,
            timezone_name=timezone_name,
        )
        self._task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def create_backup(self) -> Callable[[], Optional[Path]]:
        """Get the create_backup function."""
        return self._system["create_backup"]

    @property
    def cleanup_old_backups(self) -> Callable[[], int]:
        """Get the cleanup_old_backups function."""
        return self._system["cleanup_old_backups"]

    @property
    def list_backups(self) -> Callable[[], List[Dict]]:
        """Get the list_backups function."""
        return self._system["list_backups"]

    @property
    def get_latest_backup(self) -> Callable[[], Optional[Path]]:
        """Get the get_latest_backup function."""
        return self._system["get_latest_backup"]

    async def start(self, run_immediately: bool = True) -> None:
        """Start the backup scheduler."""
        if self._running:
            return

        self._running = True

        if run_immediately and not self._system["has_backup_today"]():
            try:
                await asyncio.to_thread(self._system["create_backup"])
            except Exception as e:
                logger.warning("Initial Backup Failed", [
                    ("Error", str(e)),
                    ("Action", "Continuing without backup"),
                ])

        try:
            await asyncio.to_thread(self._system["cleanup_old_backups"])
        except Exception as e:
            logger.warning("Backup Cleanup Failed", [
                ("Error", str(e)),
            ])

        self._task = asyncio.create_task(self._scheduler_loop())

        logger.tree("Backup Scheduler Started", [
            ("Schedule", f"Daily at {self._system['backup_hour']}:00 AM"),
            ("Retention", f"{self._system['retention_days']} days"),
            ("Prefix", self._system["backup_prefix"]),
        ], emoji="💾")

    async def stop(self) -> None:
        """Stop the backup scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop - runs daily at configured time."""
        while self._running:
            try:
                seconds_until_backup = self._system["seconds_until_next_backup"]()
                await asyncio.sleep(seconds_until_backup)

                if not self._running:
                    break

                await asyncio.to_thread(self._system["create_backup"])
                await asyncio.to_thread(self._system["cleanup_old_backups"])

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Backup Scheduler Error", [
                    ("Error", str(e)),
                ])
                await asyncio.sleep(SECONDS_PER_HOUR)


# =============================================================================
# Module Export
# =============================================================================

__all__ = [
    "create_backup_system",
    "BackupScheduler",
    "BACKUP_DIR",
    "DATABASE_PATH",
    "BACKUP_PREFIX",
    "DEFAULT_RETENTION_DAYS",
]
