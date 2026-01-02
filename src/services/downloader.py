"""
SyriaBot - Downloader Service
=============================

Downloads media from Instagram, Twitter/X, and TikTok using yt-dlp.
Compresses videos if they exceed Discord's file size limit.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import re
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.core.logger import log

# Get yt-dlp path from the same venv as the running Python
YTDLP_PATH = str(Path(sys.executable).parent / "yt-dlp")

# Cookies file for Instagram authentication
COOKIES_FILE = Path(__file__).parent.parent.parent / "cookies.txt"


# =============================================================================
# Constants
# =============================================================================

MAX_FILE_SIZE_MB = 24  # Leave headroom under Discord's 25MB limit
TEMP_DIR = Path(tempfile.gettempdir()) / "syria_dl"

# Platform detection patterns - PRE-COMPILED for performance
PLATFORM_PATTERNS = {
    "instagram": [
        re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|reels|stories)/[\w-]+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/[\w.]+/(?:p|reel)/[\w-]+", re.IGNORECASE),
    ],
    "twitter": [
        re.compile(r"(?:https?://)?(?:www\.)?(?:twitter|x)\.com/\w+/status/\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:mobile\.)?(?:twitter|x)\.com/\w+/status/\d+", re.IGNORECASE),
    ],
    "tiktok": [
        re.compile(r"(?:https?://)?(?:www\.)?tiktok\.com/@[\w.]+/video/\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:vm|vt)\.tiktok\.com/[\w]+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?tiktok\.com/t/[\w]+", re.IGNORECASE),
    ],
}

# Video file extensions (frozen set for O(1) lookup)
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"})

# Platform styling
PLATFORM_ICONS = {
    "instagram": "<:instagram:1456393259432558623>",
    "twitter": "<:x_:1456393268966346753>",
    "tiktok": "<:tiktok:1456393263744172133>",
    "unknown": "📥",
}

PLATFORM_COLORS = {
    "instagram": 0xE4405F,  # Instagram pink
    "twitter": 0x000000,    # X black
    "tiktok": 0x00F2EA,     # TikTok cyan
    "unknown": 0x5865F2,    # Discord blurple
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    files: list[Path]
    platform: str
    error: Optional[str] = None


# =============================================================================
# Downloader Service
# =============================================================================

class DownloaderService:
    """Service for downloading and processing social media content."""

    def __init__(self):
        # Ensure temp directory exists
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self._cleanup_orphaned_files()

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
                log.tree("Download Temp Cleanup", [
                    ("Files Cleaned", str(cleaned)),
                ], emoji="🧹")
        except Exception as e:
            log.tree("Download Temp Cleanup Failed", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    def get_platform(self, url: str) -> Optional[str]:
        """Detect which platform a URL belongs to."""
        for platform, patterns in PLATFORM_PATTERNS.items():
            for pattern in patterns:
                if pattern.match(url):
                    return platform
        return None

    async def download(self, url: str) -> DownloadResult:
        """
        Download media from a social media URL.

        Args:
            url: The URL to download from

        Returns:
            DownloadResult with files and status
        """
        platform = self.get_platform(url)
        if not platform:
            return DownloadResult(
                success=False,
                files=[],
                platform="unknown",
                error="Unsupported URL. Supported: Instagram, Twitter/X, TikTok."
            )

        # Create unique download directory
        download_id = str(uuid.uuid4())[:8]
        download_dir = TEMP_DIR / download_id
        download_dir.mkdir(parents=True, exist_ok=True)

        log.tree("Starting Download", [
            ("Platform", platform.title()),
            ("URL", url[:60] + "..." if len(url) > 60 else url),
            ("Download Dir", str(download_dir)),
        ], emoji="📥")

        try:
            # Build yt-dlp command
            output_template = str(download_dir / "%(title).50s_%(id)s.%(ext)s")

            cmd = [
                YTDLP_PATH,
                "--no-playlist",
                "-o", output_template,
                "--restrict-filenames",
                "--max-filesize", "100M",
                "--newline",
                "--progress",
            ]

            # Platform-specific options
            if platform == "instagram":
                if COOKIES_FILE.exists():
                    cmd.extend(["--cookies", str(COOKIES_FILE)])
                cmd.extend(["--no-check-certificates"])
            elif platform == "tiktok":
                cmd.extend(["--no-check-certificates"])

            cmd.append(url)

            # Run yt-dlp
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=120  # 2 minute timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                log.tree("Download Timeout", [
                    ("Platform", platform.title()),
                    ("URL", url[:60]),
                    ("Timeout", "120s"),
                ], emoji="⏳")
                self.cleanup([download_dir])
                return DownloadResult(
                    success=False,
                    files=[],
                    platform=platform,
                    error="Download timed out. The file may be too large."
                )

            stderr_text = stderr.decode(errors="ignore")

            if process.returncode != 0:
                error_msg = self._parse_error(stderr_text)
                log.tree("Download Failed", [
                    ("Platform", platform.title()),
                    ("Error", error_msg[:100]),
                ], emoji="❌")
                self.cleanup([download_dir])
                return DownloadResult(
                    success=False,
                    files=[],
                    platform=platform,
                    error=error_msg
                )

            # Get downloaded files
            files = list(download_dir.glob("*"))
            if not files:
                log.tree("Download No Media", [
                    ("Platform", platform.title()),
                    ("URL", url[:60]),
                    ("Reason", "No files downloaded"),
                ], emoji="⚠️")
                self.cleanup([download_dir])
                return DownloadResult(
                    success=False,
                    files=[],
                    platform=platform,
                    error="No media found in this post."
                )

            log.tree("Download Complete", [
                ("Platform", platform.title()),
                ("Files", str(len(files))),
            ], emoji="✅")

            # Process files (compress if needed)
            processed_files = []
            for file in files:
                try:
                    result = await self._process_file(file)
                    if result:
                        processed_files.append(result)
                except Exception as e:
                    log.tree("File Processing Failed", [
                        ("File", file.name),
                        ("Error", str(e)[:50]),
                    ], emoji="⚠️")

            if not processed_files:
                log.tree("Download All Files Too Large", [
                    ("Platform", platform.title()),
                    ("URL", url[:60]),
                    ("Original Files", str(len(files))),
                ], emoji="⚠️")
                self.cleanup([download_dir])
                return DownloadResult(
                    success=False,
                    files=[],
                    platform=platform,
                    error="All files were too large to upload."
                )

            return DownloadResult(
                success=True,
                files=processed_files,
                platform=platform
            )

        except Exception as e:
            log.error_tree("Download Error", e, [
                ("Platform", platform),
                ("URL", url[:60]),
            ])
            self.cleanup([download_dir])
            return DownloadResult(
                success=False,
                files=[],
                platform=platform,
                error=f"Download failed: {type(e).__name__}"
            )

    def _parse_error(self, stderr: str) -> str:
        """Parse yt-dlp error output into user-friendly message."""
        error_msg = stderr.strip() or "Download failed"

        if "Sign in to confirm you're not a bot" in error_msg or "LOGIN_REQUIRED" in error_msg:
            return "This content requires login to access."
        elif "Private" in error_msg or "login" in error_msg.lower():
            return "This content is private or requires login."
        elif "not found" in error_msg.lower() or "404" in error_msg:
            return "Content not found. It may have been deleted."
        elif "age" in error_msg.lower():
            return "This content is age-restricted."
        elif "HTTP Error 403" in error_msg:
            return "Access forbidden. The content may be restricted."
        elif "429" in error_msg or "rate" in error_msg.lower():
            return "Rate limited. Please wait a minute before trying again."

        return error_msg[:200] if len(error_msg) > 200 else error_msg

    async def _process_file(self, file: Path) -> Optional[Path]:
        """Process a downloaded file - compress if too large."""
        file_size_mb = file.stat().st_size / (1024 * 1024)

        log.tree("Processing File", [
            ("File", file.name),
            ("Size", f"{file_size_mb:.1f} MB"),
        ], emoji="⚙️")

        if file_size_mb <= MAX_FILE_SIZE_MB:
            log.tree("File Size OK", [
                ("File", file.name),
                ("Size", f"{file_size_mb:.1f} MB"),
                ("Compression", "Not needed"),
            ], emoji="✅")
            return file

        # Only compress videos
        if file.suffix.lower() not in VIDEO_EXTENSIONS:
            log.tree("File Too Large (Not Video)", [
                ("File", file.name),
                ("Size", f"{file_size_mb:.1f} MB"),
            ], emoji="⚠️")
            return None

        # Compress video
        compressed = await self._compress_video(file)
        if compressed:
            log.tree("File Compressed Successfully", [
                ("Original", file.name),
                ("Compressed", compressed.name),
            ], emoji="✅")
            file.unlink()
            return compressed

        log.tree("File Compression Failed", [
            ("File", file.name),
            ("Size", f"{file_size_mb:.1f} MB"),
            ("Result", "Skipped"),
        ], emoji="❌")
        return None

    async def _compress_video(self, file: Path) -> Optional[Path]:
        """Compress a video to fit under the size limit."""
        log.tree("Compressing Video", [
            ("File", file.name),
            ("Target", f"< {MAX_FILE_SIZE_MB} MB"),
        ], emoji="🗜️")

        output_file = file.parent / f"compressed_{file.stem}.mp4"

        # Get video duration
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file)
        ]

        try:
            probe_process = await asyncio.create_subprocess_exec(
                *probe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            probe_stdout, _ = await probe_process.communicate()
            duration = float(probe_stdout.decode().strip())
            log.tree("Video Duration Detected", [
                ("File", file.name),
                ("Duration", f"{duration:.1f}s"),
            ], emoji="⏱️")
        except Exception as e:
            duration = 60
            log.tree("Duration Probe Failed", [
                ("File", file.name),
                ("Error", str(e)[:50]),
                ("Fallback", "60s"),
            ], emoji="⚠️")

        # Calculate bitrate
        target_size_bits = MAX_FILE_SIZE_MB * 8 * 1024 * 1024
        audio_bitrate = 128 * 1024
        video_bitrate = int((target_size_bits / duration) - audio_bitrate)
        video_bitrate = max(video_bitrate, 500000)

        cmd = [
            "ffmpeg", "-y",
            "-i", str(file),
            "-c:v", "libx264",
            "-preset", "fast",
            "-b:v", str(video_bitrate),
            "-maxrate", str(int(video_bitrate * 1.5)),
            "-bufsize", str(video_bitrate * 2),
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_file)
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await asyncio.wait_for(process.communicate(), timeout=300)

            if process.returncode != 0 or not output_file.exists():
                log.tree("Compression Failed", [
                    ("File", file.name),
                ], emoji="❌")
                return None

            compressed_size_mb = output_file.stat().st_size / (1024 * 1024)

            log.tree("Compression Complete", [
                ("Original", f"{file.stat().st_size / (1024 * 1024):.1f} MB"),
                ("Compressed", f"{compressed_size_mb:.1f} MB"),
            ], emoji="✅")

            if compressed_size_mb > 25:
                log.tree("Compressed File Still Too Large", [
                    ("Size", f"{compressed_size_mb:.1f} MB"),
                ], emoji="⚠️")
                output_file.unlink()
                return None

            return output_file

        except asyncio.TimeoutError:
            log.tree("Compression Timeout", [
                ("File", file.name),
            ], emoji="⏳")
            if output_file.exists():
                output_file.unlink()
            return None
        except Exception as e:
            log.error_tree("Compression Error", e, [
                ("File", file.name),
            ])
            if output_file.exists():
                output_file.unlink()
            return None

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
                log.tree("Cleanup Failed", [
                    ("Path", str(path)),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        if cleaned > 0:
            log.tree("Cleanup Complete", [
                ("Paths Cleaned", str(cleaned)),
            ], emoji="🧹")

    async def get_video_duration(self, file: Path) -> Optional[float]:
        """Get video duration in seconds using ffprobe."""
        if file.suffix.lower() not in VIDEO_EXTENSIONS:
            return None

        try:
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file)
            ]
            process = await asyncio.create_subprocess_exec(
                *probe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
            return float(stdout.decode().strip())
        except Exception:
            return None

    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format seconds to MM:SS or HH:MM:SS."""
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format bytes to human readable size."""
        size_mb = size_bytes / (1024 * 1024)
        if size_mb >= 1:
            return f"{size_mb:.1f} MB"
        size_kb = size_bytes / 1024
        return f"{size_kb:.0f} KB"


# Global instance
downloader = DownloaderService()
