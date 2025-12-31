"""
SyriaBot - Logger
=================

Beautiful tree-style logging.

Author: حَـــــنَّـــــا
"""

import sys
from datetime import datetime
from typing import List, Tuple, Optional
from zoneinfo import ZoneInfo

from src.core.config import LOGS_DIR


TIMEZONE = ZoneInfo("America/New_York")

# ANSI colors
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
GRAY = "\033[90m"


class Logger:
    """Tree-style logger with colors."""

    def __init__(self):
        self.log_file = LOGS_DIR / "bot.log"
        self.error_file = LOGS_DIR / "bot_error.log"

    def _timestamp(self) -> str:
        """Get formatted timestamp."""
        now = datetime.now(TIMEZONE)
        return now.strftime("%I:%M:%S %p %Z")

    def _write_file(self, message: str, error: bool = False) -> None:
        """Write to log file."""
        try:
            with open(self.error_file if error else self.log_file, "a") as f:
                f.write(message + "\n")
        except Exception:
            pass

    def _format_tree(self, items: List[Tuple[str, str]]) -> str:
        """Format items as a tree."""
        if not items:
            return ""
        lines = []
        for i, (key, value) in enumerate(items):
            prefix = "└─" if i == len(items) - 1 else "├─"
            lines.append(f"  {prefix} {key}: {value}")
        return "\n".join(lines)

    def tree(self, title: str, items: List[Tuple[str, str]], emoji: str = "ℹ️") -> None:
        """Log with tree format."""
        timestamp = self._timestamp()
        tree_str = self._format_tree(items)

        # Console output with colors
        console_msg = f"{GRAY}[{timestamp}]{RESET} {emoji} {BOLD}{title}{RESET}"
        if tree_str:
            console_msg += f"\n{CYAN}{tree_str}{RESET}"
        print(console_msg)

        # File output without colors
        file_msg = f"[{timestamp}] {emoji} {title}"
        if tree_str:
            file_msg += f"\n{tree_str}"
        self._write_file(file_msg)

    def info(self, message: str) -> None:
        """Log info message."""
        timestamp = self._timestamp()
        print(f"{GRAY}[{timestamp}]{RESET} {BLUE}ℹ️{RESET} {message}")
        self._write_file(f"[{timestamp}] ℹ️ {message}")

    def success(self, message: str) -> None:
        """Log success message."""
        timestamp = self._timestamp()
        print(f"{GRAY}[{timestamp}]{RESET} {GREEN}✅{RESET} {message}")
        self._write_file(f"[{timestamp}] ✅ {message}")

    def warning(self, message: str) -> None:
        """Log warning message."""
        timestamp = self._timestamp()
        print(f"{GRAY}[{timestamp}]{RESET} {YELLOW}⚠️{RESET} {message}")
        self._write_file(f"[{timestamp}] ⚠️ {message}", error=True)

    def error(self, message: str) -> None:
        """Log error message."""
        timestamp = self._timestamp()
        print(f"{GRAY}[{timestamp}]{RESET} {RED}❌{RESET} {message}")
        self._write_file(f"[{timestamp}] ❌ {message}", error=True)


log = Logger()
