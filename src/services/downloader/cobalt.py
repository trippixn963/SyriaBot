"""
SyriaBot - Cobalt API Backend
=============================

Downloads media using local Cobalt API instance.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from pathlib import Path
from typing import Optional

import aiohttp

from src.core.logger import logger
from .config import (
    COBALT_API_URL,
    MAX_FILE_SIZE_MB,
    VIDEO_EXTENSIONS,
    DownloadResult,
)
from .video import compress_video


async def check_health() -> bool:
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
                    logger.tree("Cobalt API Health Check", [
                        ("Status", "Healthy"),
                        ("Version", version),
                    ], emoji="✅")
                    return True
                else:
                    logger.tree("Cobalt API Health Check", [
                        ("Status", "Unhealthy"),
                        ("HTTP Status", str(resp.status)),
                    ], emoji="❌")
                    return False
    except asyncio.TimeoutError:
        logger.tree("Cobalt API Health Check", [
            ("Status", "Timeout"),
            ("URL", COBALT_API_URL),
        ], emoji="❌")
        return False
    except aiohttp.ClientConnectorError as e:
        logger.tree("Cobalt API Health Check", [
            ("Status", "Connection Failed"),
            ("Error", str(e)[:50]),
        ], emoji="❌")
        return False
    except Exception as e:
        logger.tree("Cobalt API Health Check", [
            ("Status", "Error"),
            ("Error", str(e)[:50]),
        ], emoji="❌")
        return False


async def _download_single_file(
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
    logger.tree("File Download Starting", [
        ("Filename", filename[:30]),
    ], emoji="⬇️")

    try:
        async with session.get(
            download_url,
            headers={"User-Agent": "SyriaBot/1.0"},
            timeout=aiohttp.ClientTimeout(total=120),
        ) as file_resp:
            if file_resp.status != 200:
                logger.tree("File Download Failed", [
                    ("Filename", filename),
                    ("Status", str(file_resp.status)),
                ], emoji="⚠️")
                return None

            # Stream to disk for memory efficiency
            with open(file_path, 'wb') as f:
                async for chunk in file_resp.content.iter_chunked(8192):
                    f.write(chunk)

        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        logger.tree("File Downloaded", [
            ("Filename", filename[:30]),
            ("Size", f"{file_size_mb:.1f} MB"),
        ], emoji="✅")

        # Check if file is too large for Discord
        if file_size_mb > MAX_FILE_SIZE_MB:
            if file_path.suffix.lower() in VIDEO_EXTENSIONS:
                logger.tree("File Too Large, Compressing", [
                    ("Filename", filename),
                    ("Size", f"{file_size_mb:.1f} MB"),
                ], emoji="🗜️")
                compressed = await compress_video(file_path)
                if compressed:
                    file_path.unlink()
                    return compressed
                else:
                    logger.tree("Compression Failed, Skipping", [
                        ("Filename", filename),
                    ], emoji="⚠️")
                    file_path.unlink()
                    return None
            else:
                logger.tree("Non-Video Too Large, Skipping", [
                    ("Filename", filename),
                    ("Size", f"{file_size_mb:.1f} MB"),
                ], emoji="⚠️")
                file_path.unlink()
                return None
        else:
            return file_path

    except Exception as e:
        logger.tree("File Download Error", [
            ("Filename", filename),
            ("Error", str(e)[:50]),
        ], emoji="⚠️")
        if file_path.exists():
            file_path.unlink()
        return None


async def download(url: str, download_dir: Path, platform: str) -> DownloadResult:
    """Download using local Cobalt API - returns Discord-ready files."""
    try:
        logger.tree("Cobalt API Request", [
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
                    # Consume response body to properly close connection
                    await resp.read()
                    logger.tree("Cobalt API HTTP Error", [
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
            logger.tree("Cobalt API Response", [
                ("Status", status),
                ("Has URL", "Yes" if data.get("url") else "No"),
                ("Has Picker", "Yes" if data.get("picker") else "No"),
            ], emoji="📡")

            if status == "error":
                error = data.get("error", {})
                error_code = error.get("code", "unknown") if isinstance(error, dict) else str(error)
                logger.tree("Cobalt API Error Response", [
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
                logger.tree("Cobalt Response: Tunnel", [
                    ("Filename", filename[:30]),
                ], emoji="🔗")
                if download_url:
                    download_items.append((download_url, filename))

            elif status == "redirect":
                download_url = data.get("url")
                filename = data.get("filename", "video.mp4")
                logger.tree("Cobalt Response: Redirect", [
                    ("Filename", filename[:30]),
                ], emoji="🔗")
                if download_url:
                    download_items.append((download_url, filename))

            elif status == "picker":
                # Carousel/multi-item post - download ALL items
                picker = data.get("picker", [])
                logger.tree("Cobalt Response: Picker (Carousel)", [
                    ("Total Items", str(len(picker))),
                ], emoji="🎠")

                for idx, item in enumerate(picker):
                    item_url = item.get("url")
                    item_type = item.get("type", "video")
                    if item_url:
                        ext = ".mp4" if item_type == "video" else ".jpg"
                        filename = f"{item_type}_{idx + 1}{ext}"
                        download_items.append((item_url, filename))
                        logger.tree(f"Carousel Item {idx + 1}", [
                            ("Type", item_type),
                            ("Filename", filename),
                        ], emoji="📎")

            else:
                logger.tree("Cobalt Unknown Status", [
                    ("Status", str(status)),
                    ("Response Keys", ", ".join(data.keys())[:50]),
                ], emoji="⚠️")

            if not download_items:
                logger.tree("Cobalt No Download URLs", [
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
                logger.tree("Parallel Download Starting", [
                    ("Files", str(len(download_items))),
                ], emoji="⚡")
                # Download in parallel for carousels
                tasks = [
                    _download_single_file(session, url, filename, download_dir)
                    for url, filename in download_items
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                downloaded_files = [r for r in results if isinstance(r, Path)]
                failed = len([r for r in results if not isinstance(r, Path)])
                if failed > 0:
                    logger.tree("Parallel Download Partial", [
                        ("Success", str(len(downloaded_files))),
                        ("Failed", str(failed)),
                    ], emoji="⚠️")
            else:
                # Single file - download directly
                downloaded_files = []
                for download_url, filename in download_items:
                    result = await _download_single_file(session, download_url, filename, download_dir)
                    if isinstance(result, Path):
                        downloaded_files.append(result)

            if not downloaded_files:
                logger.tree("Cobalt No Files Downloaded", [
                    ("Attempted", str(len(download_items))),
                ], emoji="❌")
                return DownloadResult(
                    success=False,
                    files=[],
                    platform=platform,
                    error="Failed to download any files."
                )

            logger.tree("Cobalt Download Complete", [
                ("Platform", platform.title()),
                ("Files", str(len(downloaded_files))),
                ("Total Size", f"{sum(f.stat().st_size for f in downloaded_files) / (1024*1024):.1f} MB"),
            ], emoji="✅")

            return DownloadResult(
                success=True,
                files=downloaded_files,
                platform=platform
            )

    except aiohttp.ClientConnectorError as e:
        logger.tree("Cobalt API Connection Error", [
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
        logger.tree("Cobalt API Timeout", [
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
        logger.error_tree("Cobalt API Exception", e, [
            ("URL", COBALT_API_URL),
        ])
        return DownloadResult(
            success=False,
            files=[],
            platform=platform,
            error=f"Cobalt error: {type(e).__name__}"
        )
