"""FAQ Service package."""

from src.services.faq.service import FAQ_DATA, faq_analytics
from src.services.faq.views import FAQView, PersistentFAQView, setup_persistent_views

__all__ = ["FAQ_DATA", "faq_analytics", "FAQView", "PersistentFAQView", "setup_persistent_views"]
