"""
Database Integrity & Auto-Repair
=================================

Shared integrity checking and automatic repair for SQLite databases.
Used by the backup scheduler — checks before every backup, auto-repairs if corrupted.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Tuple

from src.core.logger import logger


def check_integrity(db_path: Path, max_retries: int = 3) -> Tuple[bool, str]:
    """
    Check SQLite database integrity with retry for transient errors.

    Args:
        db_path: Path to the database file.
        max_retries: Number of retries for transient errors (disk I/O, locked).

    Returns:
        Tuple of (is_healthy, message). message is "ok" if healthy, error string if not.
    """
    transient_errors = ("disk I/O error", "database is locked", "unable to open")

    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(str(db_path), timeout=30)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            result = conn.execute("PRAGMA integrity_check;").fetchone()[0]
            conn.close()

            if result == "ok":
                return True, "ok"
            else:
                logger.tree("Integrity Check Failed", [
                    ("Result", str(result)[:200]),
                    ("Attempt", f"{attempt + 1}/{max_retries}"),
                ], emoji="❌")
                return False, result

        except sqlite3.DatabaseError as e:
            error_str = str(e).lower()
            if any(te in error_str for te in transient_errors) and attempt < max_retries - 1:
                logger.tree("Integrity Check Transient Error", [
                    ("Error", str(e)[:100]),
                    ("Attempt", f"{attempt + 1}/{max_retries}"),
                    ("Action", "Retrying"),
                ], emoji="⚠️")
                time.sleep(2 ** attempt)
                continue
            return False, f"Database error: {e}"
        except Exception as e:
            return False, f"Check failed: {e}"

    return False, "Max retries exceeded"


def auto_repair(db_path: Path) -> bool:
    """
    Auto-repair a corrupted SQLite database via dump/restore.

    Steps:
        1. Checkpoint WAL to flush pending writes
        2. Dump all data to SQL file via iterdump()
        3. Restore into a fresh database
        4. Verify the new database passes integrity check
        5. Replace old database (keeping .pre_repair_backup)

    Args:
        db_path: Path to the corrupted database.

    Returns:
        True if repair succeeded, False otherwise.
    """
    db_str: str = str(db_path)
    dump_path: str = db_str + ".repair_dump.sql"
    new_path: str = db_str + ".repaired"
    backup_path: str = db_str + ".pre_repair_backup"

    logger.tree("Database Auto-Repair Starting", [
        ("Database", db_path.name),
        ("Action", "Dump → Restore → Verify → Replace"),
    ], emoji="🔧")

    try:
        # Step 1: Checkpoint WAL
        try:
            conn = sqlite3.connect(db_str, timeout=30)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.close()
        except Exception:
            pass  # Best-effort — WAL may not exist

        # Step 2: Dump all data to SQL
        conn = sqlite3.connect(db_str, timeout=30)
        with open(dump_path, "w") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
        conn.close()

        dump_lines = sum(1 for _ in open(dump_path))

        # Step 3: Restore into fresh DB
        new_conn = sqlite3.connect(new_path)
        with open(dump_path, "r") as f:
            new_conn.executescript(f.read())
        new_conn.close()

        # Step 4: Verify new DB
        verify_conn = sqlite3.connect(new_path)
        result = verify_conn.execute("PRAGMA integrity_check;").fetchone()[0]
        verify_conn.close()

        if result != "ok":
            logger.critical("Auto-Repair Verify Failed", [
                ("Database", db_path.name),
                ("Result", str(result)[:200]),
            ])
            _cleanup_files(new_path, dump_path)
            return False

        # Step 5: Replace old DB
        shutil.move(db_str, backup_path)
        shutil.move(new_path, db_str)

        # Cleanup dump file
        if os.path.exists(dump_path):
            os.remove(dump_path)

        logger.tree("Database Auto-Repaired", [
            ("Database", db_path.name),
            ("Lines Dumped", str(dump_lines)),
            ("Backup", backup_path),
            ("Status", "Success"),
        ], emoji="🔧")
        return True

    except Exception as e:
        logger.critical("Auto-Repair Failed", [
            ("Database", db_path.name),
            ("Error", str(e)[:200]),
        ])
        _cleanup_files(new_path, dump_path)
        return False


def check_and_repair(db_path: Path) -> Tuple[bool, str]:
    """
    Check integrity and auto-repair if corrupted. One-call convenience function.

    Args:
        db_path: Path to the database.

    Returns:
        Tuple of (is_healthy, status_message).
    """
    is_healthy, msg = check_integrity(db_path)

    if is_healthy:
        return True, "ok"

    # Attempt auto-repair
    logger.tree("Corruption Detected — Auto-Repairing", [
        ("Database", db_path.name),
        ("Integrity", msg[:100]),
    ], emoji="🚨")

    repaired = auto_repair(db_path)
    if repaired:
        return True, "repaired"
    else:
        return False, f"repair_failed: {msg}"


def _cleanup_files(*paths: str) -> None:
    """Remove temporary files, ignoring errors."""
    for path in paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
