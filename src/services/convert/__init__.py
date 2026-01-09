"""
SyriaBot - Convert Package
==========================

Image/video processing with text bars.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from src.services.convert.service import (
    ConvertService,
    ConvertResult,
    VideoInfo,
    convert_service,
    BAR_COLOR,
    TEXT_COLOR,
    WAND_AVAILABLE,
)
from src.services.convert.views import ConvertView, ConvertEditorView

__all__ = [
    "ConvertService",
    "ConvertResult",
    "VideoInfo",
    "convert_service",
    "ConvertView",
    "ConvertEditorView",
    "BAR_COLOR",
    "TEXT_COLOR",
    "WAND_AVAILABLE",
]
