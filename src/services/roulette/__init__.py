"""
SyriaBot - Roulette Minigame
============================

Random roulette minigame that spawns in general chat.
Users join via button, wheel spins, winner gets XP.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from .service import RouletteService, get_roulette_service

__all__ = ["RouletteService", "get_roulette_service"]
