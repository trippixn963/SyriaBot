"""
SyriaBot - Roulette Minigame
============================

Automatic roulette that spawns in general chat.
Participants selected from recent message activity, weighted by message count.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from .service import RouletteService, get_roulette_service

__all__ = ["RouletteService", "get_roulette_service"]
