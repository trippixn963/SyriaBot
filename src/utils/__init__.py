"""SyriaBot - Utils Package."""

from src.utils.http import http_session, DOWNLOAD_TIMEOUT
from src.utils.footer import (
    FOOTER_TEXT,
    init_footer,
    set_footer,
)
from src.utils.text import wrap_text
from src.utils.async_utils import gather_with_logging, create_safe_task
from src.utils.discord_rate_limit import (
    log_http_error,
    with_rate_limit_retry,
    RateLimitConfig,
)

__all__ = [
    # HTTP
    "http_session",
    "DOWNLOAD_TIMEOUT",
    # Footer
    "FOOTER_TEXT",
    "init_footer",
    "set_footer",
    # Text
    "wrap_text",
    # Async
    "gather_with_logging",
    "create_safe_task",
    # Rate Limit
    "log_http_error",
    "with_rate_limit_retry",
    "RateLimitConfig",
]
