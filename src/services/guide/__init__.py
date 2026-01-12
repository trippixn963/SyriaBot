"""
SyriaBot - Guide Service
========================

Interactive server guide panel with buttons.

Author: John Hamwi
Server: discord.gg/syria
"""

from src.services.guide.views import GuideView, setup_guide_views
from src.services.guide.service import GuideService, get_guide_service

__all__ = ["GuideView", "setup_guide_views", "GuideService", "get_guide_service"]
