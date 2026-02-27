"""
SyriaBot - Convert Package
==========================

Image/video processing with text bars.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from .service import (
    ConvertService,
    ConvertResult,
    VideoInfo,
    convert_service,
    BAR_COLOR,
    TEXT_COLOR,
    WAND_AVAILABLE,
)
from .views import ConvertView, VideoConvertView, start_convert_editor

__all__ = [
    "ConvertService",
    "ConvertResult",
    "VideoInfo",
    "convert_service",
    "ConvertView",
    "VideoConvertView",
    "start_convert_editor",
    "BAR_COLOR",
    "TEXT_COLOR",
    "WAND_AVAILABLE",
]
