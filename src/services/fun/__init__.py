"""
SyriaBot - Fun Commands Module
==============================

Fun interactive commands with visual cards.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from .service import fun_service
from .card import generate_ship_card, generate_meter_card, cleanup

__all__ = ["fun_service", "generate_ship_card", "generate_meter_card", "cleanup"]
