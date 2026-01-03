"""
SyriaBot - Shared Constants
===========================

Centralized constants for the entire codebase.
Import from here instead of defining locally.

Author: حَـــــنَّـــــا
"""

from zoneinfo import ZoneInfo


# =============================================================================
# Timezone
# =============================================================================

TIMEZONE_EST = ZoneInfo("America/New_York")
TIMEZONE_DAMASCUS = ZoneInfo("Asia/Damascus")


# =============================================================================
# Font Paths (System fonts, checked in order)
# =============================================================================

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux (Debian/Ubuntu)
    "/System/Library/Fonts/Helvetica.ttc",  # macOS
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",  # Arch Linux
    "arial.ttf",  # Windows fallback
]

FONT_ITALIC_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",  # Linux
    "/System/Library/Fonts/Helvetica.ttc",  # macOS (index 1)
    "/usr/share/fonts/TTF/DejaVuSans-Oblique.ttf",  # Arch Linux
    "ariali.ttf",  # Windows fallback
]


# =============================================================================
# Media File Limits
# =============================================================================

MAX_IMAGE_SIZE = 8 * 1024 * 1024    # 8MB max image input
MAX_VIDEO_SIZE = 25 * 1024 * 1024   # 25MB max video input
MAX_DIMENSION = 2000                 # Max width/height for images


# =============================================================================
# Video/GIF Processing
# =============================================================================

MAX_VIDEO_DURATION = 15  # Max video duration in seconds
GIF_FPS = 15             # Frames per second for output GIF
GIF_MAX_WIDTH = 480      # Max GIF width (height scaled proportionally)


# =============================================================================
# Convert Bar Styling (NotSoBot-style dynamic sizing)
# =============================================================================

BAR_HEIGHT_RATIO = 0.20      # Bar height = 20% of image height
MIN_BAR_HEIGHT = 80          # Minimum bar height in pixels
FONT_SIZE_RATIO = 0.70       # Font size = 70% of bar height
LINE_SPACING_RATIO = 0.25    # 25% of line height for spacing
BAR_PADDING_RATIO = 0.10     # Vertical padding = 10% of bar height
TEXT_PADDING_RATIO = 0.05    # Horizontal padding = 5% of image width

# Default colors (RGB tuples)
DEFAULT_BAR_COLOR = (255, 255, 255)   # White
DEFAULT_TEXT_COLOR = (0, 0, 0)        # Black


# =============================================================================
# Quote Image Styling
# =============================================================================

QUOTE_IMAGE_WIDTH = 1200
QUOTE_IMAGE_HEIGHT = 630

# Quote colors (RGB tuples)
QUOTE_THEME_COLOR = (15, 81, 50)       # Syria green
QUOTE_ACCENT_GOLD = (212, 175, 55)     # Gold accent
QUOTE_BG_COLOR = (0, 0, 0)             # Black background
QUOTE_TEXT_COLOR = (255, 255, 255)     # White text
QUOTE_SUBTEXT_COLOR = (156, 156, 156)  # Gray for username

# Quote layout
QUOTE_AVATAR_SECTION_WIDTH_RATIO = 0.38  # 38% for avatar side
QUOTE_MAX_BANNER_CACHE_SIZE = 10


# =============================================================================
# TempVoice Limits
# =============================================================================

TEMPVOICE_JOIN_COOLDOWN = 5                   # Seconds between channel creations
TEMPVOICE_OWNER_LEAVE_TRANSFER_DELAY = 30     # Seconds before auto-transfer
TEMPVOICE_STICKY_PANEL_THRESHOLD = 20         # Messages before re-sticking panel
TEMPVOICE_REORDER_DEBOUNCE_DELAY = 2.0        # Seconds to wait before reordering
TEMPVOICE_MAX_ALLOWED_USERS_FREE = 3          # Max allowed users for non-boosters


# =============================================================================
# Rate Limiting
# =============================================================================

WEEKLY_LIMITS = {
    "convert": 5,
    "quote": 5,
    "weather": 5,
}

# Display names for rate limit messages
RATE_LIMIT_ACTION_NAMES = {
    "convert": "Conversions",
    "quote": "Quotes",
    "weather": "Weather lookups",
}

# Emojis for rate limit messages
RATE_LIMIT_ACTION_EMOJIS = {
    "convert": "🖼️",
    "quote": "💬",
    "weather": "🌤️",
}


# =============================================================================
# Stats API
# =============================================================================

STATS_API_PORT = 8088
STATS_API_HOST = "0.0.0.0"


# =============================================================================
# Logging
# =============================================================================

LOG_RETENTION_DAYS = 7


# =============================================================================
# HTTP
# =============================================================================

HTTP_DOWNLOAD_TIMEOUT_TOTAL = 60
HTTP_DOWNLOAD_TIMEOUT_CONNECT = 10


# =============================================================================
# Supported File Extensions
# =============================================================================

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".jfif", ".bmp", ".tiff", ".tif"
}

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".webm", ".avi", ".mkv",
    ".m4v", ".flv", ".wmv", ".3gp"
}


# =============================================================================
# XP Card Colors
# =============================================================================

XP_STATUS_COLORS = {
    "online": (67, 181, 129),    # Green
    "idle": (250, 166, 26),      # Yellow/Orange
    "dnd": (240, 71, 71),        # Red
    "offline": (116, 127, 141),  # Gray
}


# =============================================================================
# Discord View/Component Timeouts
# =============================================================================

VIEW_TIMEOUT_DEFAULT = 300      # 5 minutes for interactive views
SELECT_TIMEOUT_DEFAULT = 60     # 1 minute for select menus
CLAIM_APPROVAL_TIMEOUT = 300    # 5 minutes for claim approval


# =============================================================================
# XP System Formula Constants
# =============================================================================

XP_BASE_MULTIPLIER = 100        # Base for XP formula: 100 * level^1.5
XP_COOLDOWN_CACHE_THRESHOLD = 500   # Clean cache when exceeding this size


# =============================================================================
# Processing Timeouts
# =============================================================================

VIDEO_PROCESS_TIMEOUT = 30      # FFmpeg command timeout in seconds
QUOTE_FETCH_TIMEOUT = 15        # Banner/avatar fetch timeout


# =============================================================================
# Presence System
# =============================================================================

PRESENCE_UPDATE_INTERVAL = 60   # Rotate presence status every 60 seconds
PROMO_DURATION_MINUTES = 10     # Promo message duration at top of each hour
PROMO_TEXT = "🌐 trippixn.com/syria"
