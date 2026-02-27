"""
SyriaBot - Backup Package
=========================

R2 cloud backup scheduler.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from .service import (
    BackupScheduler,
    send_backup_notification,
    DATABASE_PATH,
    BOT_NAME,
    R2_BUCKET,
    RETENTION_HOURS,
)

__all__ = [
    "BackupScheduler",
    "send_backup_notification",
    "DATABASE_PATH",
    "BOT_NAME",
    "R2_BUCKET",
    "RETENTION_HOURS",
]
