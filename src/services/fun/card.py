"""
SyriaBot - Card Generator
=========================

HTML/CSS based cards rendered with Playwright for ship, simp, howgay commands.
Shares browser instance and semaphore with rank card for efficiency.
"""

import time
from typing import Optional

from src.core.logger import logger

# Import shared browser infrastructure from rank card
from src.services.xp.card import (
    _get_page,
    _return_page,
    get_render_semaphore,
)

# Card cache for fun cards (longer TTL since results are deterministic)
_fun_cache: dict = {}
_FUN_CACHE_TTL = 300  # seconds (5 minutes - deterministic results don't change)
_MAX_CACHE_SIZE = 50  # Maximum cached cards before eviction


def _evict_cache() -> None:
    """Remove oldest entries if cache exceeds max size."""
    global _fun_cache
    if len(_fun_cache) <= _MAX_CACHE_SIZE:
        return

    # Sort by timestamp and keep newest entries
    sorted_entries = sorted(_fun_cache.items(), key=lambda x: x[1][1])
    entries_to_remove = len(_fun_cache) - _MAX_CACHE_SIZE

    for key, _ in sorted_entries[:entries_to_remove]:
        del _fun_cache[key]

    logger.tree("Fun Cache Eviction", [
        ("Removed", str(entries_to_remove)),
        ("Remaining", str(len(_fun_cache))),
    ], emoji="🧹")

# Card dimensions
SHIP_CARD_WIDTH = 700
SHIP_CARD_HEIGHT = 350
METER_CARD_WIDTH = 500
METER_CARD_HEIGHT = 320

# Viewport padding (extra space for card wrapper/shadow)
VIEWPORT_PADDING = 30

# Timeouts for waiting on assets (milliseconds)
AVATAR_LOAD_TIMEOUT_SHIP = 3000
AVATAR_LOAD_TIMEOUT_METER = 2000

# Emoji thresholds for visual feedback
HEART_EMOJI_HIGH = 70    # 💖 for >= 70%
HEART_EMOJI_MED = 40     # 💕 for >= 40%
METER_EMOJI_THRESHOLD = 50  # Different emoji above/below 50%

# Shared CSS base for all cards
_BASE_CSS = '''
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }

    body {
        font-family: 'Noto Sans', 'Noto Sans Arabic', -apple-system, BlinkMacSystemFont, sans-serif;
        background: transparent;
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
    }
'''

_GOOGLE_FONTS_LINK = '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;600;700;900&family=Noto+Sans+Arabic:wght@400;600;700&display=swap" rel="stylesheet">'


def _generate_ship_html(
    user1_name: str,
    user1_avatar: str,
    user2_name: str,
    user2_avatar: str,
    ship_name: str,
    percentage: int,
    message: str,
    banner_url: Optional[str],
) -> str:
    """Generate HTML for ship card."""
    bg_style = f'url({banner_url})' if banner_url else 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)'

    # Heart fill based on percentage
    heart_color = "#ff6b6b" if percentage >= 50 else "#ff9999"
    glow_intensity = min(percentage / 100, 1)

    html = f'''
<!DOCTYPE html>
<html>
<head>
    {_GOOGLE_FONTS_LINK}
    <style>
        {_BASE_CSS}

        .card-wrapper {{
            padding: 3px;
            background: linear-gradient(135deg, #ff6b6b, #ff8e8e, #ffb3b3, #ff6b9d);
            border-radius: 24px;
            position: relative;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4), 0 0 60px rgba(255, 107, 107, {glow_intensity * 0.3});
        }}

        .card {{
            width: {SHIP_CARD_WIDTH}px;
            height: {SHIP_CARD_HEIGHT}px;
            background: {bg_style};
            background-size: cover;
            background-position: center;
            border-radius: 21px;
            position: relative;
            overflow: hidden;
        }}

        .card::before {{
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(135deg, rgba(15, 15, 25, 0.9) 0%, rgba(20, 20, 35, 0.85) 100%);
            backdrop-filter: blur(16px);
        }}

        .card-content {{
            position: relative;
            z-index: 1;
            display: flex;
            flex-direction: column;
            height: 100%;
            padding: 28px 40px;
            align-items: center;
            justify-content: space-between;
        }}

        .title {{
            font-size: 20px;
            font-weight: 700;
            color: #ff8e8e;
            text-shadow: 0 2px 8px rgba(255, 107, 107, 0.5);
            letter-spacing: 3px;
            text-transform: uppercase;
        }}

        .avatars-section {{
            display: flex;
            align-items: center;
            gap: 24px;
        }}

        .user-column {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 12px;
        }}

        .avatar {{
            width: 110px;
            height: 110px;
            border-radius: 50%;
            object-fit: cover;
            border: 4px solid rgba(255, 107, 107, 0.6);
            box-shadow: 0 0 20px rgba(255, 107, 107, 0.3);
        }}

        .name-label {{
            font-family: 'Noto Sans', 'Noto Sans Arabic', sans-serif;
            font-size: 15px;
            font-weight: 600;
            color: #fff;
            text-shadow: 0 2px 4px rgba(0,0,0,0.5);
            max-width: 130px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            text-align: center;
        }}

        .heart-section {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
            padding: 0 16px;
        }}

        .heart {{
            font-size: 44px;
            filter: drop-shadow(0 0 12px rgba(255, 107, 107, {glow_intensity}));
        }}

        .percentage {{
            font-size: 36px;
            font-weight: 900;
            color: {heart_color};
            text-shadow: 0 2px 8px rgba(255, 107, 107, 0.5);
        }}

        .meter-section {{
            width: 100%;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .meter-bar {{
            height: 18px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 9px;
            overflow: hidden;
            position: relative;
        }}

        .meter-fill {{
            height: 100%;
            width: {percentage}%;
            background: linear-gradient(90deg, #ff6b6b, #ff8e8e, #ffb3b3);
            border-radius: 9px;
            position: relative;
            box-shadow: 0 0 16px rgba(255, 107, 107, 0.6);
        }}

        .meter-fill::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 50%;
            background: linear-gradient(180deg, rgba(255,255,255,0.3) 0%, transparent 100%);
            border-radius: 9px 9px 0 0;
        }}

        .message {{
            font-size: 18px;
            font-weight: 500;
            color: #b0b0c0;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="card-wrapper">
        <div class="card">
            <div class="card-content">
                <div class="title">COMPATIBILITY</div>

                <div class="avatars-section">
                    <div class="user-column">
                        <img class="avatar" src="{user1_avatar}" alt="avatar1">
                        <div class="name-label">{user1_name[:16]}</div>
                    </div>

                    <div class="heart-section">
                        <div class="heart">{"💖" if percentage >= HEART_EMOJI_HIGH else "💕" if percentage >= HEART_EMOJI_MED else "💔"}</div>
                        <div class="percentage">{percentage}%</div>
                    </div>

                    <div class="user-column">
                        <img class="avatar" src="{user2_avatar}" alt="avatar2">
                        <div class="name-label">{user2_name[:16]}</div>
                    </div>
                </div>

                <div class="meter-section">
                    <div class="meter-bar">
                        <div class="meter-fill"></div>
                    </div>
                </div>

                <div class="message">{message}</div>
            </div>
        </div>
    </div>
</body>
</html>
'''
    return html


def _generate_meter_html(
    user_name: str,
    user_avatar: str,
    percentage: int,
    message: str,
    meter_type: str,  # "simp" or "gay"
    banner_url: Optional[str],
) -> str:
    """Generate HTML for simp/gay meter card."""
    bg_style = f'url({banner_url})' if banner_url else 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)'

    if meter_type == "simp":
        gradient = "linear-gradient(135deg, #ff6b9d, #c850c0, #ff6b9d)"
        bar_gradient = "linear-gradient(90deg, #ff6b9d, #c850c0, #ff8ec4)"
        title = "SIMP METER"
        emoji = "🥺" if percentage >= METER_EMOJI_THRESHOLD else "😐"
        glow_color = "199, 80, 192"
    elif meter_type == "gay":
        gradient = "linear-gradient(135deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3, #a55eea)"
        bar_gradient = "linear-gradient(90deg, #ff6b6b, #ff9f43, #feca57, #2ed573, #48dbfb, #a55eea, #ff6b9d)"
        title = "GAY METER"
        emoji = "🏳️‍🌈" if percentage >= METER_EMOJI_THRESHOLD else "🌈"
        glow_color = "168, 94, 234"
    elif meter_type == "smart":
        gradient = "linear-gradient(135deg, #4facfe, #00f2fe, #4facfe)"
        bar_gradient = "linear-gradient(90deg, #4facfe, #00f2fe, #43e97b)"
        title = "SMART METER"
        emoji = "🎓" if percentage >= METER_EMOJI_THRESHOLD else "🧠"
        glow_color = "79, 172, 254"
    else:  # bodyfat
        gradient = "linear-gradient(135deg, #f093fb, #f5576c, #f093fb)"
        bar_gradient = "linear-gradient(90deg, #43e97b, #f9d423, #f5576c)"
        title = "BODY FAT"
        emoji = "🍔" if percentage >= 25 else "💪"
        glow_color = "245, 87, 108"

    html = f'''
<!DOCTYPE html>
<html>
<head>
    {_GOOGLE_FONTS_LINK}
    <style>
        {_BASE_CSS}

        .card-wrapper {{
            padding: 3px;
            background: {gradient};
            border-radius: 24px;
            position: relative;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4), 0 0 60px rgba({glow_color}, 0.25);
        }}

        .card {{
            width: {METER_CARD_WIDTH}px;
            height: {METER_CARD_HEIGHT}px;
            background: {bg_style};
            background-size: cover;
            background-position: center;
            border-radius: 21px;
            position: relative;
            overflow: hidden;
        }}

        .card::before {{
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(135deg, rgba(15, 15, 25, 0.9) 0%, rgba(20, 20, 35, 0.85) 100%);
            backdrop-filter: blur(16px);
        }}

        .card-content {{
            position: relative;
            z-index: 1;
            display: flex;
            flex-direction: column;
            height: 100%;
            padding: 24px 32px;
            align-items: center;
            justify-content: space-between;
        }}

        .title {{
            font-size: 20px;
            font-weight: 700;
            letter-spacing: 4px;
            background: {bar_gradient};
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .avatar-section {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
        }}

        .avatar {{
            width: 100px;
            height: 100px;
            border-radius: 50%;
            object-fit: cover;
            border: 4px solid rgba({glow_color}, 0.6);
            box-shadow: 0 0 20px rgba({glow_color}, 0.3);
        }}

        .user-name {{
            font-family: 'Noto Sans', 'Noto Sans Arabic', sans-serif;
            font-size: 20px;
            font-weight: 600;
            color: #fff;
            text-shadow: 0 2px 4px rgba(0,0,0,0.5);
        }}

        .result-section {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}

        .emoji {{
            font-size: 40px;
        }}

        .percentage {{
            font-size: 48px;
            font-weight: 900;
            background: {bar_gradient};
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .meter-section {{
            width: 100%;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .meter-bar {{
            height: 24px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            overflow: hidden;
            position: relative;
        }}

        .meter-fill {{
            height: 100%;
            width: {percentage}%;
            background: {bar_gradient};
            background-size: 200% 100%;
            border-radius: 12px;
            position: relative;
            box-shadow: 0 0 20px rgba({glow_color}, 0.5);
        }}

        .meter-fill::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 50%;
            background: linear-gradient(180deg, rgba(255,255,255,0.3) 0%, transparent 100%);
            border-radius: 12px 12px 0 0;
        }}

        .message {{
            font-size: 16px;
            font-weight: 500;
            color: #b0b0c0;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="card-wrapper">
        <div class="card">
            <div class="card-content">
                <div class="title">{title}</div>

                <div class="avatar-section">
                    <img class="avatar" src="{user_avatar}" alt="avatar">
                    <div class="user-name">{user_name[:16]}</div>
                </div>

                <div class="result-section">
                    <div class="emoji">{emoji}</div>
                    <div class="percentage">{percentage}%</div>
                </div>

                <div class="meter-section">
                    <div class="meter-bar">
                        <div class="meter-fill"></div>
                    </div>
                </div>

                <div class="message">{message}</div>
            </div>
        </div>
    </div>
</body>
</html>
'''
    return html


async def generate_ship_card(
    user1_id: int,
    user1_name: str,
    user1_avatar: str,
    user2_id: int,
    user2_name: str,
    user2_avatar: str,
    ship_name: str,
    percentage: int,
    message: str,
    banner_url: Optional[str] = None,
) -> bytes:
    """Generate ship card image."""
    global _fun_cache

    # Cache key uses sorted IDs for order-independence (A+B = B+A)
    cache_key = ("ship", min(user1_id, user2_id), max(user1_id, user2_id))
    now = time.time()

    if cache_key in _fun_cache:
        cached_bytes, cached_time = _fun_cache[cache_key]
        if now - cached_time < _FUN_CACHE_TTL:
            logger.tree("Ship Card Cache Hit", [
                ("Users", f"{user1_name} + {user2_name}"),
            ], emoji="⚡")
            return cached_bytes

    # Use shared semaphore from rank card module
    async with get_render_semaphore():
        page = None
        try:
            page = await _get_page()
            await page.goto('about:blank')

            html = _generate_ship_html(
                user1_name=user1_name,
                user1_avatar=user1_avatar,
                user2_name=user2_name,
                user2_avatar=user2_avatar,
                ship_name=ship_name,
                percentage=percentage,
                message=message,
                banner_url=banner_url,
            )

            await page.set_viewport_size({'width': SHIP_CARD_WIDTH + VIEWPORT_PADDING, 'height': SHIP_CARD_HEIGHT + VIEWPORT_PADDING})
            await page.set_content(html, wait_until='networkidle')

            # Wait for avatars
            try:
                await page.wait_for_function(
                    '''() => {
                        const imgs = document.querySelectorAll('img.avatar');
                        return Array.from(imgs).every(img => img.complete && img.naturalWidth > 0);
                    }''',
                    timeout=AVATAR_LOAD_TIMEOUT_SHIP
                )
            except Exception:
                pass

            screenshot = await page.screenshot(type='png', omit_background=True)
            await _return_page(page)
            page = None

            _fun_cache[cache_key] = (screenshot, now)
            _evict_cache()

            logger.tree("Ship Card Generated", [
                ("Users", f"{user1_name} + {user2_name}"),
                ("Result", f"{percentage}%"),
            ], emoji="💕")

            return screenshot

        except Exception as e:
            logger.tree("Ship Card Failed", [
                ("Error", str(e)[:100]),
            ], emoji="❌")
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            raise


async def generate_meter_card(
    user_id: int,
    guild_id: int,
    user_name: str,
    user_avatar: str,
    percentage: int,
    message: str,
    meter_type: str,
    banner_url: Optional[str] = None,
) -> bytes:
    """Generate simp/gay meter card image."""
    global _fun_cache

    # Cache key uses user_id + guild_id + type for stable identification
    cache_key = (meter_type, user_id, guild_id)
    now = time.time()

    if cache_key in _fun_cache:
        cached_bytes, cached_time = _fun_cache[cache_key]
        if now - cached_time < _FUN_CACHE_TTL:
            logger.tree(f"{meter_type.title()} Card Cache Hit", [
                ("User", user_name),
            ], emoji="⚡")
            return cached_bytes

    # Use shared semaphore from rank card module
    async with get_render_semaphore():
        page = None
        try:
            page = await _get_page()
            await page.goto('about:blank')

            html = _generate_meter_html(
                user_name=user_name,
                user_avatar=user_avatar,
                percentage=percentage,
                message=message,
                meter_type=meter_type,
                banner_url=banner_url,
            )

            await page.set_viewport_size({'width': METER_CARD_WIDTH + VIEWPORT_PADDING, 'height': METER_CARD_HEIGHT + VIEWPORT_PADDING})
            await page.set_content(html, wait_until='networkidle')

            # Wait for avatar
            try:
                await page.wait_for_function(
                    '''() => {
                        const img = document.querySelector('img.avatar');
                        return img && img.complete && img.naturalWidth > 0;
                    }''',
                    timeout=AVATAR_LOAD_TIMEOUT_METER
                )
            except Exception:
                pass

            screenshot = await page.screenshot(type='png', omit_background=True)
            await _return_page(page)
            page = None

            _fun_cache[cache_key] = (screenshot, now)
            _evict_cache()

            logger.tree(f"{meter_type.title()} Card Generated", [
                ("User", user_name),
                ("Result", f"{percentage}%"),
            ], emoji="🎨")

            return screenshot

        except Exception as e:
            logger.tree(f"{meter_type.title()} Card Failed", [
                ("Error", str(e)[:100]),
            ], emoji="❌")
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            raise


async def cleanup():
    """Clean up fun card cache."""
    global _fun_cache
    _fun_cache.clear()
    logger.tree("Fun Card Cache Cleared", [], emoji="🧹")
