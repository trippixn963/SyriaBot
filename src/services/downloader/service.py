"""
SyriaBot - Downloader Service
=============================

Main coordinator for downloading media from social media platforms.
Tries Cobalt API first, falls back to yt-dlp.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import shutil
import uuid
from pathlib import Path

from src.core.logger import logger
from .config import (
    TEMP_DIR,
    COBALT_API_URL,
    MAX_FILE_SIZE_MB,
    VIDEO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    DownloadResult,
    get_platform,
)
from . import cobalt
from . import ytdlp


class DownloaderService:
    """Service for downloading and processing social media content."""

    def __init__(self):
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self._cleanup_orphaned_files()
        logger.tree("Downloader Service Initialized", [
            ("Cobalt API", COBALT_API_URL),
            ("Temp Dir", str(TEMP_DIR)),
            ("Max Size", f"{MAX_FILE_SIZE_MB} MB"),
        ], emoji="📥")

    def _cleanup_orphaned_files(self) -> None:
        """Clean up any leftover temp files from previous runs."""
        try:
            cleaned = 0
            for item in TEMP_DIR.iterdir():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    cleaned += 1
                elif item.is_file():
                    item.unlink(missing_ok=True)
                    cleaned += 1
            if cleaned > 0:
                logger.tree("Download Temp Cleanup", [
                    ("Files Cleaned", str(cleaned)),
                ], emoji="🧹")
        except Exception as e:
            logger.tree("Download Temp Cleanup Failed", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    def get_platform(self, url: str) -> str | None:
        """Detect which platform a URL belongs to."""
        platform = get_platform(url)
        if not platform:
            logger.tree("URL Platform Not Detected", [
                ("URL", url[:60]),
                ("Supported", "Instagram, Twitter, TikTok, Reddit, Facebook, Snapchat, Twitch"),
            ], emoji="⚠️")
        return platform

    async def check_cobalt_health(self) -> bool:
        """Check if Cobalt API is healthy and responsive."""
        return await cobalt.check_health()

    async def download(self, url: str) -> DownloadResult:
        """
        Download media from a social media URL using Cobalt API.
        Falls back to yt-dlp if Cobalt fails.
        """
        platform = self.get_platform(url)
        if not platform:
            logger.tree("Download Rejected", [
                ("Reason", "Unsupported URL"),
                ("URL", url[:60]),
            ], emoji="❌")
            return DownloadResult(
                success=False,
                files=[],
                platform="unknown",
                error="Unsupported URL. Supported: Instagram, Twitter, TikTok, Reddit, Facebook, Snapchat, Twitch."
            )

        # Create unique download directory
        download_id = str(uuid.uuid4())[:8]
        download_dir = TEMP_DIR / download_id
        download_dir.mkdir(parents=True, exist_ok=True)

        logger.tree("Download Started", [
            ("Platform", platform.title()),
            ("URL", url[:60] + "..." if len(url) > 60 else url),
            ("Download ID", download_id),
        ], emoji="📥")

        # Try Cobalt API first (fast, returns Discord-ready files)
        cobalt_result = await cobalt.download(url, download_dir, platform)
        if cobalt_result.success:
            # Rename files with platform + server ad
            renamed_files = self._rename_files_for_branding(cobalt_result.files, platform)
            logger.tree("Download Success (Cobalt)", [
                ("Platform", platform.title()),
                ("Files", str(len(renamed_files))),
            ], emoji="✅")
            return DownloadResult(
                success=True,
                files=renamed_files,
                platform=platform
            )

        logger.tree("Cobalt Failed, Trying yt-dlp Fallback", [
            ("Platform", platform.title()),
            ("Cobalt Error", cobalt_result.error[:50] if cobalt_result.error else "Unknown"),
        ], emoji="🔄")

        # Fallback to yt-dlp
        ytdlp_result = await ytdlp.download(url, download_dir, platform)
        if ytdlp_result.success:
            # Rename files with platform + server ad
            renamed_files = self._rename_files_for_branding(ytdlp_result.files, platform)
            logger.tree("Download Success (yt-dlp)", [
                ("Platform", platform.title()),
                ("Files", str(len(renamed_files))),
            ], emoji="✅")
            return DownloadResult(
                success=True,
                files=renamed_files,
                platform=platform
            )
        else:
            logger.tree("Download Failed (Both Methods)", [
                ("Platform", platform.title()),
                ("Error", ytdlp_result.error[:50] if ytdlp_result.error else "Unknown"),
            ], emoji="❌")
            self.cleanup([download_dir])

        return ytdlp_result

    def _rename_files_for_branding(self, files: list[Path], platform: str) -> list[Path]:
        """
        Rename files with platform name and server advertisement.
        Format: {Platform}_discord.gg-syria_{number}.{ext}
        """
        if not files:
            return files

        renamed = []
        for idx, file in enumerate(files, 1):
            ext = file.suffix.lower()

            # Determine file type for naming
            if ext in VIDEO_EXTENSIONS:
                file_type = "video"
            elif ext in IMAGE_EXTENSIONS:
                file_type = "image"
            else:
                file_type = "media"

            # Build new filename: Platform_discord.gg-syria_1.mp4
            # Use hyphen instead of slash for filename compatibility
            new_name = f"{platform.title()}_{file_type}_discord.gg-syria_{idx}{ext}"
            new_path = file.parent / new_name

            try:
                file.rename(new_path)
                renamed.append(new_path)
                logger.tree("File Renamed for Branding", [
                    ("Original", file.name[:30]),
                    ("New Name", new_name[:40]),
                ], emoji="🏷️")
            except Exception as e:
                logger.tree("File Rename Failed", [
                    ("File", file.name[:30]),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
                renamed.append(file)  # Keep original if rename fails

        return renamed

    def cleanup(self, paths: list[Path]) -> None:
        """Clean up downloaded files and directories."""
        cleaned = 0
        for path in paths:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                    cleaned += 1
                elif path.exists():
                    path.unlink()
                    cleaned += 1
            except Exception as e:
                logger.tree("Cleanup Failed", [
                    ("Path", str(path)[:50]),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        if cleaned > 0:
            logger.tree("Cleanup Complete", [
                ("Paths Cleaned", str(cleaned)),
            ], emoji="🧹")

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format bytes to human readable size."""
        size_mb = size_bytes / (1024 * 1024)
        if size_mb >= 1:
            return f"{size_mb:.1f} MB"
        size_kb = size_bytes / 1024
        return f"{size_kb:.0f} KB"
