"""
SyriaBot - Downloader Service
=============================

Downloads media from social media platforms using Cobalt API.
Supported: Instagram, Twitter/X, TikTok, Reddit, Facebook, Snapchat, Twitch.
Falls back to yt-dlp if Cobalt fails.

Features:
- Parallel carousel downloads for faster multi-file posts
- Streaming downloads for memory efficiency
- Auto-compression for files over Discord's limit
- Branded filenames with server advertisement

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import aiohttp
import re
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.core.logger import log


# =============================================================================
# Configuration
# =============================================================================

# yt-dlp path from the same venv as the running Python
YTDLP_PATH = str(Path(sys.executable).parent / "yt-dlp")

# gallery-dl for image downloads (fallback when yt-dlp fails on images)
GALLERY_DL_PATH = "/usr/bin/gallery-dl"

# Cookies file for Instagram authentication
COOKIES_FILE = Path(__file__).parent.parent.parent / "cookies.txt"

# Cobalt API - local self-hosted instance
COBALT_API_URL = "http://localhost:9000"


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
    "reddit": [
        re.compile(r"(?:https?://)?(?:www\.)?reddit\.com/r/\w+/comments/\w+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:old\.)?reddit\.com/r/\w+/comments/\w+", re.IGNORECASE),
        re.compile(r"(?:https?://)?v\.redd\.it/\w+", re.IGNORECASE),
    ],
    "facebook": [
        re.compile(r"(?:https?://)?(?:www\.)?facebook\.com/.+/videos/\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?facebook\.com/watch/?\?v=\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?facebook\.com/reel/\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?fb\.watch/[\w-]+", re.IGNORECASE),
    ],
    "snapchat": [
        re.compile(r"(?:https?://)?(?:www\.)?snapchat\.com/spotlight/[\w-]+", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?snapchat\.com/t/[\w-]+", re.IGNORECASE),
    ],
    "twitch": [
        re.compile(r"(?:https?://)?(?:www\.)?twitch\.tv/\w+/clip/[\w-]+", re.IGNORECASE),
        re.compile(r"(?:https?://)?clips\.twitch\.tv/[\w-]+", re.IGNORECASE),
    ],
}

# Video file extensions (frozen set for O(1) lookup)
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"})

# Image file extensions
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})


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
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self._cleanup_orphaned_files()
        log.tree("Downloader Service Initialized", [
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
        log.tree("URL Platform Not Detected", [
            ("URL", url[:60]),
            ("Supported", "Instagram, Twitter, TikTok, Reddit, Facebook, Snapchat, Twitch"),
        ], emoji="⚠️")
        return None

    async def check_cobalt_health(self) -> bool:
        """Check if Cobalt API is healthy and responsive."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    COBALT_API_URL,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        version = data.get("version", "unknown")
                        log.tree("Cobalt API Health Check", [
                            ("Status", "Healthy"),
                            ("Version", version),
                        ], emoji="✅")
                        return True
                    else:
                        log.tree("Cobalt API Health Check", [
                            ("Status", "Unhealthy"),
                            ("HTTP Status", str(resp.status)),
                        ], emoji="❌")
                        return False
        except asyncio.TimeoutError:
            log.tree("Cobalt API Health Check", [
                ("Status", "Timeout"),
                ("URL", COBALT_API_URL),
            ], emoji="❌")
            return False
        except aiohttp.ClientConnectorError as e:
            log.tree("Cobalt API Health Check", [
                ("Status", "Connection Failed"),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False
        except Exception as e:
            log.tree("Cobalt API Health Check", [
                ("Status", "Error"),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False

    async def _download_single_file(
        self,
        session: aiohttp.ClientSession,
        download_url: str,
        filename: str,
        download_dir: Path
    ) -> Optional[Path]:
        """
        Download a single file with streaming for memory efficiency.
        Returns the Path on success, None on failure.
        """
        file_path = download_dir / filename
        log.tree("File Download Starting", [
            ("Filename", filename[:30]),
        ], emoji="⬇️")

        try:
            async with session.get(
                download_url,
                headers={"User-Agent": "SyriaBot/1.0"},
                timeout=aiohttp.ClientTimeout(total=120),
            ) as file_resp:
                if file_resp.status != 200:
                    log.tree("File Download Failed", [
                        ("Filename", filename),
                        ("Status", str(file_resp.status)),
                    ], emoji="⚠️")
                    return None

                # Stream to disk for memory efficiency
                with open(file_path, 'wb') as f:
                    async for chunk in file_resp.content.iter_chunked(8192):
                        f.write(chunk)

            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            log.tree("File Downloaded", [
                ("Filename", filename[:30]),
                ("Size", f"{file_size_mb:.1f} MB"),
            ], emoji="✅")

            # Check if file is too large for Discord
            if file_size_mb > MAX_FILE_SIZE_MB:
                if file_path.suffix.lower() in VIDEO_EXTENSIONS:
                    log.tree("File Too Large, Compressing", [
                        ("Filename", filename),
                        ("Size", f"{file_size_mb:.1f} MB"),
                    ], emoji="🗜️")
                    compressed = await self._compress_video(file_path)
                    if compressed:
                        file_path.unlink()
                        return compressed
                    else:
                        log.tree("Compression Failed, Skipping", [
                            ("Filename", filename),
                        ], emoji="⚠️")
                        file_path.unlink()
                        return None
                else:
                    log.tree("Non-Video Too Large, Skipping", [
                        ("Filename", filename),
                        ("Size", f"{file_size_mb:.1f} MB"),
                    ], emoji="⚠️")
                    file_path.unlink()
                    return None
            else:
                return file_path

        except Exception as e:
            log.tree("File Download Error", [
                ("Filename", filename),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")
            if file_path.exists():
                file_path.unlink()
            return None

    async def download(self, url: str) -> DownloadResult:
        """
        Download media from a social media URL using Cobalt API.
        Falls back to yt-dlp if Cobalt fails.
        """
        platform = self.get_platform(url)
        if not platform:
            log.tree("Download Rejected", [
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

        log.tree("Download Started", [
            ("Platform", platform.title()),
            ("URL", url[:60] + "..." if len(url) > 60 else url),
            ("Download ID", download_id),
        ], emoji="📥")

        # Try Cobalt API first (fast, returns Discord-ready files)
        cobalt_result = await self._download_cobalt(url, download_dir, platform)
        if cobalt_result.success:
            log.tree("Download Success (Cobalt)", [
                ("Platform", platform.title()),
                ("Files", str(len(cobalt_result.files))),
            ], emoji="✅")
            return cobalt_result

        log.tree("Cobalt Failed, Trying yt-dlp Fallback", [
            ("Platform", platform.title()),
            ("Cobalt Error", cobalt_result.error[:50] if cobalt_result.error else "Unknown"),
        ], emoji="🔄")

        # Fallback to yt-dlp
        ytdlp_result = await self._download_ytdlp(url, download_dir, platform)
        if ytdlp_result.success:
            log.tree("Download Success (yt-dlp)", [
                ("Platform", platform.title()),
                ("Files", str(len(ytdlp_result.files))),
            ], emoji="✅")
        else:
            log.tree("Download Failed (Both Methods)", [
                ("Platform", platform.title()),
                ("Error", ytdlp_result.error[:50] if ytdlp_result.error else "Unknown"),
            ], emoji="❌")
        return ytdlp_result

    async def _download_cobalt(self, url: str, download_dir: Path, platform: str) -> DownloadResult:
        """Download using local Cobalt API - returns Discord-ready files."""
        try:
            log.tree("Cobalt API Request", [
                ("Platform", platform.title()),
                ("URL", url[:50]),
                ("API", COBALT_API_URL),
            ], emoji="🌐")

            async with aiohttp.ClientSession() as session:
                # Request video from local Cobalt
                async with session.post(
                    COBALT_API_URL,
                    json={"url": url},
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        log.tree("Cobalt API HTTP Error", [
                            ("Status", str(resp.status)),
                            ("URL", COBALT_API_URL),
                        ], emoji="❌")
                        return DownloadResult(
                            success=False,
                            files=[],
                            platform=platform,
                            error=f"Cobalt API returned status {resp.status}"
                        )

                    data = await resp.json()

                # Log full API response for debugging
                status = data.get("status")
                log.tree("Cobalt API Response", [
                    ("Status", status),
                    ("Has URL", "Yes" if data.get("url") else "No"),
                    ("Has Picker", "Yes" if data.get("picker") else "No"),
                ], emoji="📡")

                if status == "error":
                    error = data.get("error", {})
                    error_code = error.get("code", "unknown") if isinstance(error, dict) else str(error)
                    log.tree("Cobalt API Error Response", [
                        ("Error Code", str(error_code)[:50]),
                        ("Full Error", str(error)[:100]),
                    ], emoji="❌")
                    return DownloadResult(
                        success=False,
                        files=[],
                        platform=platform,
                        error=f"Cobalt error: {error_code}"
                    )

                # Collect all download URLs
                download_items = []  # List of (url, filename) tuples

                if status == "tunnel":
                    download_url = data.get("url")
                    filename = data.get("filename", "video.mp4")
                    log.tree("Cobalt Response: Tunnel", [
                        ("Filename", filename[:30]),
                    ], emoji="🔗")
                    if download_url:
                        download_items.append((download_url, filename))

                elif status == "redirect":
                    download_url = data.get("url")
                    filename = data.get("filename", "video.mp4")
                    log.tree("Cobalt Response: Redirect", [
                        ("Filename", filename[:30]),
                    ], emoji="🔗")
                    if download_url:
                        download_items.append((download_url, filename))

                elif status == "picker":
                    # Carousel/multi-item post - download ALL items
                    picker = data.get("picker", [])
                    log.tree("Cobalt Response: Picker (Carousel)", [
                        ("Total Items", str(len(picker))),
                    ], emoji="🎠")

                    for idx, item in enumerate(picker):
                        item_url = item.get("url")
                        item_type = item.get("type", "video")
                        if item_url:
                            ext = ".mp4" if item_type == "video" else ".jpg"
                            filename = f"{item_type}_{idx + 1}{ext}"
                            download_items.append((item_url, filename))
                            log.tree(f"Carousel Item {idx + 1}", [
                                ("Type", item_type),
                                ("Filename", filename),
                            ], emoji="📎")

                else:
                    log.tree("Cobalt Unknown Status", [
                        ("Status", str(status)),
                        ("Response Keys", ", ".join(data.keys())[:50]),
                    ], emoji="⚠️")

                if not download_items:
                    log.tree("Cobalt No Download URLs", [
                        ("Status", status),
                        ("Response", str(data)[:100]),
                    ], emoji="❌")
                    return DownloadResult(
                        success=False,
                        files=[],
                        platform=platform,
                        error="Cobalt returned no download URL"
                    )

                # Download all files (parallel for multiple items)
                if len(download_items) > 1:
                    log.tree("Parallel Download Starting", [
                        ("Files", str(len(download_items))),
                    ], emoji="⚡")
                    # Download in parallel for carousels
                    tasks = [
                        self._download_single_file(session, url, filename, download_dir)
                        for url, filename in download_items
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    downloaded_files = [r for r in results if isinstance(r, Path)]
                    failed = len([r for r in results if not isinstance(r, Path)])
                    if failed > 0:
                        log.tree("Parallel Download Partial", [
                            ("Success", str(len(downloaded_files))),
                            ("Failed", str(failed)),
                        ], emoji="⚠️")
                else:
                    # Single file - download directly
                    downloaded_files = []
                    for download_url, filename in download_items:
                        result = await self._download_single_file(session, download_url, filename, download_dir)
                        if isinstance(result, Path):
                            downloaded_files.append(result)

                if not downloaded_files:
                    log.tree("Cobalt No Files Downloaded", [
                        ("Attempted", str(len(download_items))),
                    ], emoji="❌")
                    self.cleanup([download_dir])
                    return DownloadResult(
                        success=False,
                        files=[],
                        platform=platform,
                        error="Failed to download any files."
                    )

                # Rename files with platform + server ad
                renamed_files = self._rename_files_for_branding(downloaded_files, platform)

                log.tree("Cobalt Download Complete", [
                    ("Platform", platform.title()),
                    ("Files", str(len(renamed_files))),
                    ("Total Size", f"{sum(f.stat().st_size for f in renamed_files) / (1024*1024):.1f} MB"),
                ], emoji="✅")

                return DownloadResult(
                    success=True,
                    files=renamed_files,
                    platform=platform
                )

        except aiohttp.ClientConnectorError as e:
            log.tree("Cobalt API Connection Error", [
                ("Error", str(e)[:50]),
                ("URL", COBALT_API_URL),
                ("Hint", "Is Cobalt container running?"),
            ], emoji="❌")
            return DownloadResult(
                success=False,
                files=[],
                platform=platform,
                error=f"Cobalt connection failed: {type(e).__name__}"
            )
        except asyncio.TimeoutError:
            log.tree("Cobalt API Timeout", [
                ("Timeout", "30s"),
                ("URL", COBALT_API_URL),
            ], emoji="⏳")
            return DownloadResult(
                success=False,
                files=[],
                platform=platform,
                error="Cobalt request timed out"
            )
        except Exception as e:
            log.error_tree("Cobalt API Exception", e, [
                ("URL", COBALT_API_URL),
            ])
            return DownloadResult(
                success=False,
                files=[],
                platform=platform,
                error=f"Cobalt error: {type(e).__name__}"
            )

    async def _download_ytdlp(self, url: str, download_dir: Path, platform: str) -> DownloadResult:
        """Download using yt-dlp as fallback."""
        try:
            output_template = str(download_dir / "%(title).50s_%(id)s.%(ext)s")

            cmd = [
                YTDLP_PATH,
                "--no-playlist",
                "-o", output_template,
                "--restrict-filenames",
                "--max-filesize", "100M",
                "--newline",
                "--progress",
                "-f", "bv[vcodec^=avc]+ba/bv*+ba/b",
                "--merge-output-format", "mp4",
            ]

            if platform == "instagram":
                if COOKIES_FILE.exists():
                    cmd.extend(["--cookies", str(COOKIES_FILE)])
                    log.tree("yt-dlp Using Cookies", [
                        ("Platform", "Instagram"),
                    ], emoji="🍪")
                cmd.extend(["--no-check-certificates"])
            elif platform == "tiktok":
                cmd.extend(["--no-check-certificates"])

            cmd.append(url)

            log.tree("yt-dlp Started", [
                ("Platform", platform.title()),
                ("URL", url[:50]),
            ], emoji="🎬")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=120
                )
            except asyncio.TimeoutError:
                process.kill()
                log.tree("yt-dlp Timeout", [
                    ("Platform", platform.title()),
                    ("Timeout", "120s"),
                ], emoji="⏳")
                self.cleanup([download_dir])
                return DownloadResult(
                    success=False,
                    files=[],
                    platform=platform,
                    error="Download timed out."
                )

            stderr_text = stderr.decode(errors="ignore")

            if process.returncode != 0:
                log.tree("yt-dlp Non-Zero Exit", [
                    ("Platform", platform.title()),
                    ("Exit Code", str(process.returncode)),
                ], emoji="⚠️")

                if "No video formats found" in stderr_text:
                    log.tree("yt-dlp No Video, Trying Images", [
                        ("Platform", platform.title()),
                    ], emoji="🖼️")
                    image_result = await self._download_images(url, download_dir, platform)
                    if image_result.success:
                        return image_result
                    self.cleanup([download_dir])
                    return image_result

                error_msg = self._parse_error(stderr_text)
                log.tree("yt-dlp Failed", [
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

            files = list(download_dir.glob("*"))
            if not files:
                log.tree("yt-dlp No Files Downloaded", [
                    ("Platform", platform.title()),
                    ("Download Dir", str(download_dir)),
                ], emoji="⚠️")
                self.cleanup([download_dir])
                return DownloadResult(
                    success=False,
                    files=[],
                    platform=platform,
                    error="No media found in this post."
                )

            log.tree("yt-dlp Download Complete", [
                ("Platform", platform.title()),
                ("Files", str(len(files))),
                ("Names", ", ".join(f.name[:20] for f in files[:3])),
            ], emoji="✅")

            # Process files
            processed_files = []
            for file in files:
                try:
                    result = await self._process_file(file)
                    if result:
                        processed_files.append(result)
                except Exception as e:
                    log.tree("yt-dlp File Processing Failed", [
                        ("File", file.name),
                        ("Error", str(e)[:50]),
                    ], emoji="⚠️")

            if not processed_files:
                log.tree("yt-dlp All Files Too Large", [
                    ("Platform", platform.title()),
                    ("Original Files", str(len(files))),
                ], emoji="❌")
                self.cleanup([download_dir])
                return DownloadResult(
                    success=False,
                    files=[],
                    platform=platform,
                    error="All files were too large to upload."
                )

            # Rename files with platform + server ad
            renamed_files = self._rename_files_for_branding(processed_files, platform)

            return DownloadResult(
                success=True,
                files=renamed_files,
                platform=platform
            )

        except FileNotFoundError:
            log.tree("yt-dlp Not Found", [
                ("Path", YTDLP_PATH),
            ], emoji="❌")
            self.cleanup([download_dir])
            return DownloadResult(
                success=False,
                files=[],
                platform=platform,
                error="yt-dlp not installed"
            )
        except Exception as e:
            log.error_tree("yt-dlp Exception", e, [
                ("Platform", platform),
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

        if "No video formats found" in error_msg:
            return "This post contains only images, not video."
        elif "Sign in to confirm you're not a bot" in error_msg or "LOGIN_REQUIRED" in error_msg:
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

    async def _download_images(self, url: str, download_dir: Path, platform: str) -> DownloadResult:
        """Download images using gallery-dl (fallback when yt-dlp fails on image posts)."""
        log.tree("Image Download Started", [
            ("Platform", platform.title()),
            ("URL", url[:60]),
            ("Tool", "gallery-dl"),
        ], emoji="🖼️")

        cmd = [
            GALLERY_DL_PATH,
            "--directory", str(download_dir),
            "--filename", "{filename}.{extension}",
            "--no-mtime",
        ]

        if COOKIES_FILE.exists():
            cmd.extend(["--cookies", str(COOKIES_FILE)])
            log.tree("Image Download Using Cookies", [
                ("Platform", platform.title()),
            ], emoji="🍪")

        cmd.append(url)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=60
                )
            except asyncio.TimeoutError:
                process.kill()
                log.tree("Image Download Timeout", [
                    ("Platform", platform.title()),
                    ("Timeout", "60s"),
                ], emoji="⏳")
                return DownloadResult(
                    success=False,
                    files=[],
                    platform=platform,
                    error="Image download timed out."
                )

            stderr_text = stderr.decode(errors="ignore")

            if process.returncode != 0:
                log.tree("Image Download Failed", [
                    ("Platform", platform.title()),
                    ("Exit Code", str(process.returncode)),
                    ("Error", stderr_text[:100] if stderr_text else "Unknown"),
                ], emoji="❌")

                if "401" in stderr_text or "login" in stderr_text.lower():
                    return DownloadResult(
                        success=False,
                        files=[],
                        platform=platform,
                        error="This content requires login to access."
                    )
                elif "404" in stderr_text or "not found" in stderr_text.lower():
                    return DownloadResult(
                        success=False,
                        files=[],
                        platform=platform,
                        error="Content not found. It may have been deleted."
                    )

                return DownloadResult(
                    success=False,
                    files=[],
                    platform=platform,
                    error="Failed to download images from this post."
                )

            # Get downloaded files
            files = []
            for ext in IMAGE_EXTENSIONS:
                files.extend(download_dir.rglob(f"*{ext}"))

            if not files:
                log.tree("Image Download No Files", [
                    ("Platform", platform.title()),
                ], emoji="⚠️")
                return DownloadResult(
                    success=False,
                    files=[],
                    platform=platform,
                    error="No images found in this post."
                )

            # Move files to download_dir root if in subdirectories
            processed_files = []
            files_moved = 0
            for file in files:
                if file.parent != download_dir:
                    new_path = download_dir / file.name
                    counter = 1
                    while new_path.exists():
                        new_path = download_dir / f"{file.stem}_{counter}{file.suffix}"
                        counter += 1
                    shutil.move(str(file), str(new_path))
                    processed_files.append(new_path)
                    files_moved += 1
                else:
                    processed_files.append(file)

            if files_moved > 0:
                log.tree("Image Files Reorganized", [
                    ("Files Moved", str(files_moved)),
                ], emoji="📁")

            # Clean up subdirectories
            for item in download_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)

            # Rename files with platform + server ad
            renamed_files = self._rename_files_for_branding(processed_files, platform)

            log.tree("Image Download Complete", [
                ("Platform", platform.title()),
                ("Images", str(len(renamed_files))),
            ], emoji="✅")

            return DownloadResult(
                success=True,
                files=renamed_files,
                platform=platform
            )

        except FileNotFoundError:
            log.tree("Image Download Tool Not Found", [
                ("Tool", "gallery-dl"),
                ("Path", GALLERY_DL_PATH),
            ], emoji="❌")
            return DownloadResult(
                success=False,
                files=[],
                platform=platform,
                error="Image download tool not available."
            )
        except Exception as e:
            log.error_tree("Image Download Exception", e, [
                ("Platform", platform),
            ])
            return DownloadResult(
                success=False,
                files=[],
                platform=platform,
                error=f"Image download failed: {type(e).__name__}"
            )

    async def _process_file(self, file: Path) -> Optional[Path]:
        """Process a downloaded file - re-encode videos for Discord compatibility."""
        file_size_mb = file.stat().st_size / (1024 * 1024)

        log.tree("Processing File", [
            ("File", file.name),
            ("Size", f"{file_size_mb:.1f} MB"),
            ("Type", file.suffix.lower()),
        ], emoji="⚙️")

        # Non-video files: just check size
        if file.suffix.lower() not in VIDEO_EXTENSIONS:
            if file_size_mb <= MAX_FILE_SIZE_MB:
                log.tree("File Ready (Non-Video)", [
                    ("File", file.name),
                    ("Size", f"{file_size_mb:.1f} MB"),
                ], emoji="✅")
                return file
            log.tree("File Too Large (Non-Video)", [
                ("File", file.name),
                ("Size", f"{file_size_mb:.1f} MB"),
                ("Max", f"{MAX_FILE_SIZE_MB} MB"),
            ], emoji="❌")
            return None

        # Video files need processing for Discord compatibility
        needs_compression = file_size_mb > MAX_FILE_SIZE_MB

        if needs_compression:
            log.tree("Video Needs Compression", [
                ("File", file.name),
                ("Size", f"{file_size_mb:.1f} MB"),
                ("Target", f"< {MAX_FILE_SIZE_MB} MB"),
            ], emoji="🗜️")
            result = await self._compress_video(file)
        else:
            result = await self._ensure_discord_compatible(file)

        if result:
            result_size = result.stat().st_size / (1024 * 1024)
            log.tree("Video Processing Success", [
                ("Original", file.name),
                ("Result", result.name),
                ("Original Size", f"{file_size_mb:.1f} MB"),
                ("Result Size", f"{result_size:.1f} MB"),
            ], emoji="✅")
            if result != file:
                file.unlink()
            return result

        log.tree("Video Processing Failed", [
            ("File", file.name),
            ("Size", f"{file_size_mb:.1f} MB"),
        ], emoji="❌")
        return None

    async def _check_video_format(self, file: Path) -> tuple[str, str]:
        """Check video codec and pixel format using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,pix_fmt",
            "-of", "csv=p=0",
            str(file)
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
            output = stdout.decode().strip()
            parts = output.split(",")
            if len(parts) >= 2:
                return parts[0], parts[1]
            log.tree("ffprobe Parse Error", [
                ("Output", output[:50]),
            ], emoji="⚠️")
            return "unknown", "unknown"
        except asyncio.TimeoutError:
            log.tree("ffprobe Timeout", [
                ("File", file.name),
            ], emoji="⏳")
            return "unknown", "unknown"
        except Exception as e:
            log.tree("ffprobe Error", [
                ("File", file.name),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")
            return "unknown", "unknown"

    async def _ensure_discord_compatible(self, file: Path) -> Optional[Path]:
        """Ensure video is Discord-compatible. Only re-encodes if necessary."""
        codec, pix_fmt = await self._check_video_format(file)

        log.tree("Video Format Check", [
            ("File", file.name),
            ("Codec", codec),
            ("Pixel Format", pix_fmt),
        ], emoji="🔍")

        is_h264 = codec.lower() == "h264"
        is_yuv420p = pix_fmt.lower() == "yuv420p"

        output_file = file.parent / f"discord_{file.stem}.mp4"

        if is_h264 and is_yuv420p:
            log.tree("Video Compatible, Remuxing", [
                ("File", file.name),
                ("Action", "Copy video + encode audio to AAC"),
            ], emoji="🔄")
            cmd = [
                "ffmpeg", "-y",
                "-i", str(file),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(output_file)
            ]
            timeout = 60
        else:
            log.tree("Video Incompatible, Re-encoding", [
                ("File", file.name),
                ("Codec", f"{codec} -> h264"),
                ("PixFmt", f"{pix_fmt} -> yuv420p"),
            ], emoji="🔄")
            cmd = [
                "ffmpeg", "-y",
                "-i", str(file),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(output_file)
            ]
            timeout = 120

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

            if process.returncode != 0 or not output_file.exists():
                stderr_text = stderr.decode(errors="ignore")
                log.tree("ffmpeg Processing Failed", [
                    ("File", file.name),
                    ("Exit Code", str(process.returncode)),
                    ("Error", stderr_text[:100] if stderr_text else "Unknown"),
                ], emoji="❌")
                if output_file.exists():
                    output_file.unlink()
                return None

            new_size_mb = output_file.stat().st_size / (1024 * 1024)
            log.tree("ffmpeg Processing Complete", [
                ("Original", f"{file.stat().st_size / (1024*1024):.1f} MB"),
                ("Result", f"{new_size_mb:.1f} MB"),
                ("Method", "Remux" if (is_h264 and is_yuv420p) else "Re-encode"),
            ], emoji="✅")

            if new_size_mb > MAX_FILE_SIZE_MB:
                log.tree("Processed File Too Large", [
                    ("Size", f"{new_size_mb:.1f} MB"),
                    ("Max", f"{MAX_FILE_SIZE_MB} MB"),
                ], emoji="⚠️")
                compressed = await self._compress_video(output_file)
                output_file.unlink()
                return compressed

            return output_file

        except asyncio.TimeoutError:
            log.tree("ffmpeg Timeout", [
                ("File", file.name),
                ("Timeout", f"{timeout}s"),
            ], emoji="⏳")
            if output_file.exists():
                output_file.unlink()
            return None
        except Exception as e:
            log.error_tree("ffmpeg Exception", e, [
                ("File", file.name),
            ])
            if output_file.exists():
                output_file.unlink()
            return None

    async def _compress_video(self, file: Path) -> Optional[Path]:
        """Compress a video to fit under the size limit."""
        log.tree("Video Compression Started", [
            ("File", file.name),
            ("Current Size", f"{file.stat().st_size / (1024*1024):.1f} MB"),
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
                ("Duration", f"{duration:.1f}s"),
            ], emoji="⏱️")
        except Exception as e:
            duration = 60
            log.tree("Duration Probe Failed", [
                ("Error", str(e)[:50]),
                ("Using Default", "60s"),
            ], emoji="⚠️")

        # Calculate target bitrate
        target_size_bits = MAX_FILE_SIZE_MB * 8 * 1024 * 1024
        audio_bitrate = 128 * 1024
        video_bitrate = int((target_size_bits / duration) - audio_bitrate)
        video_bitrate = max(video_bitrate, 500000)

        log.tree("Compression Bitrate Calculated", [
            ("Video Bitrate", f"{video_bitrate // 1000} kbps"),
            ("Audio Bitrate", "128 kbps"),
        ], emoji="📊")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(file),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-b:v", str(video_bitrate),
            "-maxrate", str(int(video_bitrate * 1.5)),
            "-bufsize", str(video_bitrate * 2),
            "-pix_fmt", "yuv420p",
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
                    ("Exit Code", str(process.returncode)),
                ], emoji="❌")
                if output_file.exists():
                    output_file.unlink()
                return None

            compressed_size_mb = output_file.stat().st_size / (1024 * 1024)

            log.tree("Compression Complete", [
                ("Original", f"{file.stat().st_size / (1024*1024):.1f} MB"),
                ("Compressed", f"{compressed_size_mb:.1f} MB"),
                ("Reduction", f"{(1 - compressed_size_mb / (file.stat().st_size / (1024*1024))) * 100:.0f}%"),
            ], emoji="✅")

            if compressed_size_mb > 25:
                log.tree("Compressed Still Too Large", [
                    ("Size", f"{compressed_size_mb:.1f} MB"),
                    ("Max", "25 MB"),
                ], emoji="❌")
                output_file.unlink()
                return None

            return output_file

        except asyncio.TimeoutError:
            log.tree("Compression Timeout", [
                ("File", file.name),
                ("Timeout", "300s"),
            ], emoji="⏳")
            if output_file.exists():
                output_file.unlink()
            return None
        except Exception as e:
            log.error_tree("Compression Exception", e, [
                ("File", file.name),
            ])
            if output_file.exists():
                output_file.unlink()
            return None

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
                log.tree("File Renamed for Branding", [
                    ("Original", file.name[:30]),
                    ("New Name", new_name[:40]),
                ], emoji="🏷️")
            except Exception as e:
                log.tree("File Rename Failed", [
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
                log.tree("Cleanup Failed", [
                    ("Path", str(path)[:50]),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        if cleaned > 0:
            log.tree("Cleanup Complete", [
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


# Global instance
downloader = DownloaderService()
