"""
SyriaBot - FAQ Package
======================

FAQ system with persistent views.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from .service import FAQ_DATA, faq_analytics
from .views import FAQView, PersistentFAQView, setup_persistent_views

__all__ = ["FAQ_DATA", "faq_analytics", "FAQView", "PersistentFAQView", "setup_persistent_views"]
