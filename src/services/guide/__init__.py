"""
SyriaBot - Guide Service
========================

Interactive server guide panel with buttons.

Author: John Hamwi
Server: discord.gg/syria
"""

from src.services.guide.views import GuideView, setup_guide_views

__all__ = ["GuideView", "setup_guide_views"]
