"""
SyriaBot - yt-dlp Backend
=========================

Downloads media using yt-dlp and gallery-dl fallback for images.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import shutil
from pathlib import Path
from typing import Optional

from src.core.logger import log
from .config import (
    YTDLP_PATH,
    GALLERY_DL_PATH,
    COOKIES_FILE,
    IMAGE_EXTENSIONS,
    DownloadResult,
)
from .video import process_file


def parse_error(stderr: str) -> str:
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


async def download_images(url: str, download_dir: Path, platform: str) -> DownloadResult:
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

        log.tree("Image Download Complete", [
            ("Platform", platform.title()),
            ("Images", str(len(processed_files))),
        ], emoji="✅")

        return DownloadResult(
            success=True,
            files=processed_files,
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


async def download(url: str, download_dir: Path, platform: str) -> DownloadResult:
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
                return await download_images(url, download_dir, platform)

            error_msg = parse_error(stderr_text)
            log.tree("yt-dlp Failed", [
                ("Platform", platform.title()),
                ("Error", error_msg[:100]),
            ], emoji="❌")
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
                result = await process_file(file)
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

    except FileNotFoundError:
        log.tree("yt-dlp Not Found", [
            ("Path", YTDLP_PATH),
        ], emoji="❌")
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
        return DownloadResult(
            success=False,
            files=[],
            platform=platform,
            error=f"Download failed: {type(e).__name__}"
        )
