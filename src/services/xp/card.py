"""
XP System - Rank Card Generator
===============================

HTML/CSS based rank card rendered with Playwright for professional quality.
Optimized with page pooling and caching for fast generation.
"""

import asyncio
import atexit
import time
from typing import Optional
from playwright.async_api import async_playwright

from src.core.logger import log


# Status colors
STATUS_COLORS = {
    "online": "#3ba55c",
    "idle": "#faa61a",
    "dnd": "#ed4245",
    "offline": "#747f8d",
    "streaming": "#9146ff",
}

# Keep browser and context alive for performance
_browser = None
_context = None
_playwright = None

# Page pool for reuse (avoid creating/destroying pages)
_page_pool: list = []
_page_pool_lock = asyncio.Lock()
_MAX_POOL_SIZE = 2  # Reduced from 3 to save memory

# Card cache: {cache_key: (bytes, timestamp)}
_card_cache: dict = {}
_CACHE_TTL = 30  # Cache cards for 30 seconds

# Track last activity for idle timeout
_last_activity: float = 0
_IDLE_TIMEOUT = 120  # Close browser after 2 minutes of inactivity (was 5 min)

# Track renders for periodic browser restart (clears memory leaks)
_render_count: int = 0
_RESTART_AFTER_RENDERS = 50  # Restart browser every 50 renders

# Semaphore to limit concurrent card generations (prevents race conditions)
_render_semaphore: asyncio.Semaphore = None


def get_render_semaphore() -> asyncio.Semaphore:
    """Get or create the shared render semaphore."""
    global _render_semaphore
    if _render_semaphore is None:
        _render_semaphore = asyncio.Semaphore(1)  # Reduced from 2 to save memory
    return _render_semaphore


def _sync_cleanup():
    """Synchronous cleanup for atexit/signal handlers."""
    import subprocess
    try:
        # Kill any orphaned chrome-headless-shell processes owned by this user
        subprocess.run(
            ['pkill', '-f', 'chrome-headless-shell'],
            capture_output=True,
            timeout=5
        )
    except Exception:
        pass


# Register cleanup handlers
atexit.register(_sync_cleanup)


async def _check_idle_timeout():
    """Check if browser should be closed due to inactivity."""
    global _last_activity
    if _browser is not None and _last_activity > 0:
        idle_time = time.time() - _last_activity
        if idle_time > _IDLE_TIMEOUT:
            log.tree("Rank Card Browser Idle", [
                ("Idle Time", f"{int(idle_time)}s"),
                ("Action", "Closing browser"),
            ], emoji="💤")
            await cleanup()


async def _check_render_restart():
    """Check if browser should be restarted due to render count (memory cleanup)."""
    global _render_count
    if _browser is not None and _render_count >= _RESTART_AFTER_RENDERS:
        log.tree("Rank Card Browser Restart", [
            ("Render Count", str(_render_count)),
            ("Action", "Restarting for memory cleanup"),
        ], emoji="🔄")
        await cleanup()
        _render_count = 0


async def _get_context():
    """Get or create browser context (reusable)."""
    global _browser, _context, _playwright, _last_activity

    # Note: cleanup checks are now done in _get_page() before calling this
    # to prevent race conditions with the page pool

    if _context is None:
        log.tree("Rank Card Browser Starting", [
            ("Action", "Launching Chromium"),
        ], emoji="🚀")

        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-extensions',
                '--disable-background-networking',
                '--disable-sync',
                '--disable-translate',
                '--hide-scrollbars',
                '--metrics-recording-only',
                '--mute-audio',
                '--no-first-run',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--disable-component-update',
                '--disable-default-apps',
                '--disable-hang-monitor',
                '--disable-popup-blocking',
                '--disable-prompt-on-repost',
                '--js-flags=--max-old-space-size=128',
            ]
        )
        _context = await _browser.new_context(
            viewport={'width': 960, 'height': 300},
            device_scale_factor=1,
        )

        log.tree("Rank Card Browser Ready", [
            ("Status", "Chromium launched"),
        ], emoji="✅")

    _last_activity = time.time()
    return _context


async def _get_page():
    """Get a page from pool or create new one."""
    # First, run cleanup checks BEFORE getting a page
    # This ensures we don't get a page that's about to become stale
    await _check_idle_timeout()
    await _check_render_restart()

    async with _page_pool_lock:
        while _page_pool:
            page = _page_pool.pop()
            # Verify page is still connected
            try:
                if not page.is_closed():
                    return page
            except Exception:
                pass
            # Page is stale, discard it

    context = await _get_context()
    return await context.new_page()


async def _return_page(page):
    """Return page to pool for reuse."""
    # Don't pool closed/invalid pages
    try:
        if page.is_closed():
            return
    except Exception:
        return

    async with _page_pool_lock:
        if len(_page_pool) < _MAX_POOL_SIZE:
            _page_pool.append(page)
        else:
            try:
                await page.close()
            except Exception:
                pass


def _generate_html(
    display_name: str,
    username: str,
    avatar_url: str,
    level: int,
    rank: int,
    current_xp: int,
    xp_for_next: int,
    xp_progress: float,
    total_messages: int,
    voice_minutes: int,
    is_booster: bool,
    banner_url: Optional[str],
    status: str,
) -> str:
    """Generate HTML for rank card."""

    status_color = STATUS_COLORS.get(status, STATUS_COLORS["online"])
    progress_percent = int(xp_progress * 100)

    # Background style
    bg_style = f'url({banner_url})' if banner_url else 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)'

    # Booster badge HTML
    booster_badge = ""
    if is_booster:
        booster_badge = '''
                        <div class="badge booster-badge">
                            <span class="badge-label">Booster</span>
                            <span class="badge-value booster">2x</span>
                        </div>
        '''

    html = f'''
<!DOCTYPE html>
<html>
<head>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', Ubuntu, sans-serif;
            background: transparent;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }}

        .card-wrapper {{
            padding: 3px;
            background: linear-gradient(135deg, #43b581, #57f287, #f5d55a, #e6a83a);
            border-radius: 24px;
            position: relative;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4), 0 0 60px rgba(67, 181, 129, 0.2), 0 0 60px rgba(245, 213, 90, 0.15);
        }}

        .card-wrapper::before {{
            content: '';
            position: absolute;
            inset: -8px;
            border-radius: 32px;
            background: linear-gradient(135deg, #43b58155, #57f28744, #f5d55a55, #e6a83a44);
            filter: blur(20px);
            opacity: 0.8;
            z-index: -1;
        }}

        .card {{
            width: 934px;
            height: 280px;
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
            background: linear-gradient(135deg, rgba(15, 15, 25, 0.85) 0%, rgba(20, 20, 35, 0.8) 100%);
            backdrop-filter: blur(16px);
        }}

        .card-content {{
            position: relative;
            z-index: 1;
            display: flex;
            height: 100%;
            padding: 32px 40px;
            gap: 36px;
        }}

        /* Avatar Section */
        .avatar-section {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}

        .avatar-wrapper {{
            position: relative;
            width: 180px;
            height: 180px;
        }}

        .avatar-ring {{
            position: absolute;
            inset: -6px;
            border-radius: 50%;
            border: 6px solid {status_color};
            background: transparent;
        }}

        .avatar-ring::before {{
            content: '';
            position: absolute;
            inset: -12px;
            border-radius: 50%;
            background: {status_color};
            filter: blur(20px);
            opacity: 0.4;
            z-index: -1;
        }}

        .avatar {{
            width: 180px;
            height: 180px;
            border-radius: 50%;
            object-fit: cover;
            position: relative;
            z-index: 1;
        }}

        .status-dot {{
            position: absolute;
            bottom: 5px;
            right: 5px;
            width: 44px;
            height: 44px;
            background: {status_color};
            border: 8px solid #14141f;
            border-radius: 50%;
            z-index: 3;
            box-shadow: 0 0 12px {status_color}66;
        }}

        /* Info Section */
        .info-section {{
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
            gap: 24px;
        }}

        /* Top Row - Name and Badges */
        .top-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .names {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}

        .display-name {{
            font-family: 'Amiri', 'Noto Sans Arabic', 'Noto Sans', serif;
            font-size: 56px;
            font-weight: 700;
            color: #fff;
            text-shadow: 0 2px 8px rgba(0,0,0,0.4);
            line-height: 1.1;
        }}

        .username {{
            font-size: 24px;
            font-weight: 500;
            color: #8a8a9a;
        }}

        .badges {{
            display: flex;
            gap: 10px;
            align-items: center;
        }}

        .badge {{
            display: flex;
            flex-direction: column;
            align-items: center;
            border-radius: 14px;
            padding: 10px 20px;
            min-width: 85px;
            position: relative;
            overflow: hidden;
        }}

        .badge.rank-badge {{
            background: linear-gradient(145deg, #4a4a5a, #3a3a4a, #5a5a6a);
            border: 1px solid rgba(255,255,255,0.15);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.1);
        }}

        .badge.rank-badge::after {{
            content: '';
            position: absolute;
            top: 0;
            left: -50%;
            width: 30%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent);
            transform: skewX(-20deg);
        }}

        .badge.level-badge {{
            background: linear-gradient(145deg, #f5d55a, #e6a83a, #d4982a);
            border: 1px solid rgba(255,255,255,0.3);
            box-shadow: 0 4px 16px rgba(230, 168, 58, 0.4), inset 0 1px 0 rgba(255,255,255,0.3);
        }}

        .badge.level-badge::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 20%;
            width: 30%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
            transform: skewX(-20deg);
        }}

        .badge.booster-badge {{
            background: linear-gradient(145deg, #ff73fa, #c850ff, #a855f7);
            border: 1px solid rgba(255,255,255,0.3);
            box-shadow: 0 4px 16px rgba(200, 80, 255, 0.5), inset 0 1px 0 rgba(255,255,255,0.3);
        }}

        .badge.booster-badge::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 20%;
            width: 30%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
            transform: skewX(-20deg);
        }}

        .badge-label {{
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 2px;
        }}

        .badge.rank-badge .badge-label {{
            color: #9a9aaa;
        }}

        .badge.level-badge .badge-label {{
            color: rgba(0,0,0,0.5);
        }}

        .badge.booster-badge .badge-label {{
            color: rgba(255,255,255,0.8);
        }}

        .badge-value {{
            font-size: 26px;
            font-weight: 900;
        }}

        .badge-value.rank {{
            color: #fff;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }}

        .badge-value.level {{
            color: #1a1a2e;
            text-shadow: 0 1px 0 rgba(255,255,255,0.3);
        }}

        .badge-value.booster {{
            color: #fff;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }}

        /* Progress Section */
        .progress-section {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .progress-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .xp-text {{
            font-size: 18px;
            font-weight: 600;
            color: #b0b0c0;
        }}

        .xp-text span {{
            color: #57f287;
            font-weight: 700;
        }}

        .progress-percent {{
            font-size: 22px;
            font-weight: 800;
            color: #57f287;
        }}

        .progress-bar {{
            height: 28px;
            background: rgba(255,255,255,0.08);
            border-radius: 14px;
            overflow: hidden;
            position: relative;
            border: 1px solid rgba(255,255,255,0.05);
        }}

        .progress-fill {{
            height: 100%;
            width: {progress_percent}%;
            background: linear-gradient(90deg,
                #2d9f5e 0%,
                #43b581 25%,
                #57f287 50%,
                #43b581 75%,
                #2d9f5e 100%
            );
            background-size: 200% 100%;
            border-radius: 14px;
            position: relative;
            min-width: 28px;
            box-shadow: 0 0 24px rgba(87, 242, 135, 0.5);
            overflow: hidden;
        }}

        .progress-fill::before {{
            content: '';
            position: absolute;
            top: -50%;
            left: -20%;
            width: 40%;
            height: 200%;
            background: linear-gradient(
                105deg,
                transparent 40%,
                rgba(255,255,255,0.5) 50%,
                transparent 60%
            );
            transform: skewX(-25deg);
        }}

        .progress-fill::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 50%;
            background: linear-gradient(180deg, rgba(255,255,255,0.25) 0%, transparent 100%);
            border-radius: 14px 14px 0 0;
        }}
    </style>
</head>
<body>
    <div class="card-wrapper">
    <div class="card">
        <div class="card-content">
            <div class="avatar-section">
                <div class="avatar-wrapper">
                    <div class="avatar-ring"></div>
                    <img class="avatar" src="{avatar_url}" alt="avatar">
                    <div class="status-dot"></div>
                </div>
            </div>

            <div class="info-section">
                <div class="top-row">
                    <div class="names">
                        <div class="display-name">{display_name}</div>
                        <div class="username">@{username}</div>
                    </div>
                    <div class="badges">
                        <div class="badge rank-badge">
                            <span class="badge-label">Rank</span>
                            <span class="badge-value rank">#{rank}</span>
                        </div>
                        <div class="badge level-badge">
                            <span class="badge-label">Level</span>
                            <span class="badge-value level">{level}</span>
                        </div>
                        {booster_badge}
                    </div>
                </div>

                <div class="progress-section">
                    <div class="progress-header">
                        <span class="xp-text"><span>{current_xp:,}</span> / {xp_for_next:,} XP</span>
                        <span class="progress-percent">{progress_percent}%</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    </div>
</body>
</html>
'''
    return html


async def generate_rank_card(
    username: str,
    display_name: str,
    avatar_url: str,
    level: int,
    rank: int,
    current_xp: int,
    xp_for_next: int,
    xp_progress: float,
    total_messages: int,
    voice_minutes: int,
    is_booster: bool = False,
    guild_id: Optional[int] = None,
    banner_url: Optional[str] = None,
    status: str = "online",
) -> bytes:
    """Generate rank card using Playwright with caching and page pooling."""
    global _card_cache

    # Create cache key from data that affects appearance
    cache_key = (
        username, display_name, level, rank, current_xp,
        xp_for_next, is_booster, status, avatar_url[:50]
    )

    # Check cache
    now = time.time()
    if cache_key in _card_cache:
        cached_bytes, cached_time = _card_cache[cache_key]
        if now - cached_time < _CACHE_TTL:
            log.tree("Rank Card Cache Hit", [
                ("User", display_name),
            ], emoji="⚡")
            return cached_bytes

    # Clean old cache entries periodically
    if len(_card_cache) > 100:
        _card_cache.clear()

    # Use semaphore to limit concurrent renders
    async with get_render_semaphore():
        page = None
        try:
            page = await _get_page()

            # Clear page before each render to prevent stale content
            await page.goto('about:blank')

            # Reset viewport size (fun cards may have changed it)
            await page.set_viewport_size({'width': 960, 'height': 300})

            # Generate HTML
            html = _generate_html(
                display_name=display_name[:20] + "..." if len(display_name) > 20 else display_name,
                username=username,
                avatar_url=avatar_url,
                level=level,
                rank=rank,
                current_xp=current_xp,
                xp_for_next=xp_for_next,
                xp_progress=xp_progress,
                total_messages=total_messages,
                voice_minutes=voice_minutes,
                is_booster=is_booster,
                banner_url=banner_url,
                status=status,
            )

            await page.set_content(html, wait_until='networkidle')

            # Wait for avatar with shorter timeout (2s instead of 5s)
            try:
                await page.wait_for_function(
                    '''() => {
                        const img = document.querySelector('img.avatar');
                        return img && img.complete && img.naturalWidth > 0;
                    }''',
                    timeout=2000
                )
            except Exception:
                # Quick fallback - don't log every time
                await page.evaluate('''(initial) => {
                    const img = document.querySelector('img.avatar');
                    if (img) {
                        img.style.display = 'none';
                        const wrapper = document.querySelector('.avatar-wrapper');
                        if (wrapper) {
                            const fallback = document.createElement('div');
                            fallback.style.cssText = 'width:180px;height:180px;border-radius:50%;background:linear-gradient(135deg,#3a3a4a,#2a2a3a);display:flex;align-items:center;justify-content:center;font-size:64px;color:#fff;font-weight:700;';
                            fallback.textContent = initial;
                            wrapper.insertBefore(fallback, img);
                        }
                    }
                }''', display_name[0].upper() if display_name else "?")

            # Screenshot
            screenshot = await page.screenshot(type='png', omit_background=True)

            # Increment render count for memory management
            global _render_count
            _render_count += 1

            # Return page to pool instead of closing
            await _return_page(page)
            page = None

            # Cache the result
            _card_cache[cache_key] = (screenshot, now)

            log.tree("Rank Card Generated", [
                ("User", display_name),
                ("Level", str(level)),
                ("Renders", str(_render_count)),
            ], emoji="🎨")

            return screenshot

        except Exception as e:
            log.tree("Rank Card Failed", [
                ("User", display_name),
                ("Error", str(e)[:100]),
            ], emoji="❌")
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            raise


async def cleanup():
    """Clean up browser resources. Call on bot shutdown."""
    global _browser, _context, _playwright, _page_pool, _card_cache, _last_activity

    # Reset activity timer
    _last_activity = 0

    # Close all pooled pages
    async with _page_pool_lock:
        for page in _page_pool:
            try:
                await page.close()
            except Exception:
                pass
        _page_pool.clear()

    # Close browser and playwright
    if _context:
        try:
            await _context.close()
        except Exception:
            pass
        _context = None

    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None

    if _playwright:
        try:
            await _playwright.stop()
        except Exception:
            pass
        _playwright = None

    # Clear cache
    _card_cache.clear()

    # Force kill any remaining chrome processes as safety net
    _sync_cleanup()

    log.tree("Rank Card Cleanup", [("Status", "Browser closed")], emoji="🧹")
