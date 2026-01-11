"""FAQ Service package."""

from src.services.faq.service import FAQ_DATA, faq_analytics
from src.services.faq.views import FAQView

__all__ = ["FAQ_DATA", "faq_analytics", "FAQView"]
