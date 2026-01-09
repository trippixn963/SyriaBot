"""
SyriaBot - Video Processing
===========================

FFmpeg-based video processing: format checking, compatibility, compression.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from pathlib import Path
from typing import Optional

from src.core.logger import log
from .config import MAX_FILE_SIZE_MB, VIDEO_EXTENSIONS


async def check_video_format(file: Path) -> tuple[str, str]:
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


async def get_video_duration(file: Path) -> float:
    """Get video duration in seconds using ffprobe."""
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
        return duration
    except Exception as e:
        log.tree("Duration Probe Failed", [
            ("Error", str(e)[:50]),
            ("Using Default", "60s"),
        ], emoji="⚠️")
        return 60.0


async def ensure_discord_compatible(file: Path) -> Optional[Path]:
    """Ensure video is Discord-compatible. Only re-encodes if necessary."""
    codec, pix_fmt = await check_video_format(file)

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
            compressed = await compress_video(output_file)
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


async def compress_video(file: Path) -> Optional[Path]:
    """Compress a video to fit under the size limit."""
    log.tree("Video Compression Started", [
        ("File", file.name),
        ("Current Size", f"{file.stat().st_size / (1024*1024):.1f} MB"),
        ("Target", f"< {MAX_FILE_SIZE_MB} MB"),
    ], emoji="🗜️")

    output_file = file.parent / f"compressed_{file.stem}.mp4"
    duration = await get_video_duration(file)

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


async def process_file(file: Path) -> Optional[Path]:
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
        result = await compress_video(file)
    else:
        result = await ensure_discord_compatible(file)

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
