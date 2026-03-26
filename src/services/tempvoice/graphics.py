"""
SyriaBot - TempVoice Guide Graphics
====================================

CSS-rendered guide images for voice controls and music commands.
Transparent PNG with gold/green accents — matches the rules banners.
Reuses the rank card Playwright browser infrastructure.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from src.core.logger import logger
from src.services.xp.card import _get_page, _return_page, get_render_semaphore


# =============================================================================
# Guide Data
# =============================================================================

VOICE_CONTROLS = [
    ("LOCK", "Lock / unlock your channel"),
    ("LIMIT", "Set user limit"),
    ("RENAME", "Rename channel (boosters only)"),
    ("ALLOW", "Add trusted users"),
    ("BLOCK", "Block users"),
    ("KICK", "Kick from channel"),
    ("CLAIM", "Claim ownerless channel"),
    ("TRANSFER", "Transfer ownership"),
    ("CLEAR", "Clear chat messages"),
]

MUSIC_COMMANDS = [
    ("/PLAY", "Play a song or a playlist"),
    ("/SKIP", "Skip to the next track"),
    ("/QUEUE", "View the current queue"),
    ("/PAUSE", "Pause the current track"),
    ("/RESUME", "Resume playback"),
    ("/STOP", "Stop and disconnect"),
    ("/LOOP", "Set repeat mode"),
    ("/SHUFFLE", "Shuffle the queue"),
    ("/LYRICS", "Show song lyrics"),
]


# =============================================================================
# HTML Template — transparent background, gold/green style
# =============================================================================

def _build_guide_html(title: str, subtitle: str, items: list[tuple[str, str]]) -> str:
    """Build HTML for a guide image — transparent bg, gold title, green subtitle, card grid."""

    cards_html = ""
    for name, desc in items:
        cards_html += f"""
            <div class="card">
                <div class="card-name">{name}</div>
                <div class="card-desc">{desc}</div>
            </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
<style>
    @font-face {{ font-family: 'Playfair Display'; src: url('file:///usr/share/fonts/truetype/playfair/PlayfairDisplay-Variable.ttf'); font-weight: 900; }}
    @font-face {{ font-family: 'Inter'; src: url('file:///usr/share/fonts/truetype/inter/Inter-Regular.ttf'); font-weight: 400; }}
    @font-face {{ font-family: 'Inter'; src: url('file:///usr/share/fonts/truetype/inter/Inter-SemiBold.ttf'); font-weight: 600; }}
    @font-face {{ font-family: 'Inter'; src: url('file:///usr/share/fonts/truetype/inter/Inter-Bold.ttf'); font-weight: 700; }}

    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
        background: transparent;
        font-family: 'Inter', sans-serif;
        width: 900px;
        padding: 30px 40px 34px;
    }}

    /* Gold accent line above title */
    .gold-line {{
        width: 50px;
        height: 3px;
        background: linear-gradient(90deg, #C5A028, #D4AF37, #C5A028);
        border-radius: 2px;
        margin: 0 auto 14px;
    }}

    .title {{
        text-align: center;
        font-family: 'Playfair Display', Georgia, serif;
        font-weight: 900;
        font-size: 42px;
        letter-spacing: 4px;
        text-transform: uppercase;
        background: linear-gradient(180deg, #D4AF37 0%, #B8932A 50%, #C5A028 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 8px;
        line-height: 1.1;
    }}

    .subtitle {{
        text-align: center;
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        font-size: 12px;
        letter-spacing: 3.5px;
        text-transform: uppercase;
        color: #1F5E2E;
        margin-bottom: 8px;
    }}

    /* Green accent line below subtitle */
    .green-line {{
        width: 45px;
        height: 2px;
        background: #1F5E2E;
        border-radius: 1px;
        margin: 0 auto 26px;
    }}

    .grid {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 12px;
    }}

    .card {{
        border: 1px solid rgba(212, 175, 55, 0.25);
        border-left: 3px solid #D4AF37;
        border-radius: 10px;
        padding: 16px 18px;
        background: rgba(212, 175, 55, 0.04);
    }}

    .card-name {{
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        font-size: 15px;
        letter-spacing: 0.5px;
        background: linear-gradient(180deg, #D4AF37 0%, #B8932A 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 5px;
    }}

    .card-desc {{
        font-family: 'Inter', sans-serif;
        font-weight: 400;
        font-size: 12px;
        color: #888;
        line-height: 1.3;
    }}
</style>
</head>
<body>
    <div class="gold-line"></div>
    <div class="title">{title}</div>
    <div class="subtitle">{subtitle}</div>
    <div class="green-line"></div>
    <div class="grid">
        {cards_html}
    </div>
</body>
</html>"""


# =============================================================================
# Render Functions
# =============================================================================

async def render_voice_guide() -> bytes | None:
    """Render the voice controls guide image."""
    return await _render_guide("Voice Controls", "Channel Management", VOICE_CONTROLS)


async def render_music_guide() -> bytes | None:
    """Render the music commands guide image."""
    return await _render_guide("Music Commands", "Boogie Premium", MUSIC_COMMANDS)


async def _render_guide(title: str, subtitle: str, items: list[tuple[str, str]]) -> bytes | None:
    """Render a guide to transparent PNG bytes."""
    semaphore = get_render_semaphore()
    page = None

    try:
        async with semaphore:
            page = await _get_page()
            await page.goto('about:blank')

            rows = (len(items) + 2) // 3
            height = 160 + rows * 95

            await page.set_viewport_size({'width': 900, 'height': height})

            html = _build_guide_html(title, subtitle, items)
            await page.set_content(html, wait_until='networkidle')

            try:
                await page.wait_for_timeout(400)
            except Exception:
                pass

            # omit_background=True for transparent PNG
            screenshot = await page.screenshot(type='png', omit_background=True)

            await _return_page(page)
            page = None

            logger.tree("TempVoice Guide Rendered", [
                ("Title", title),
                ("Cards", str(len(items))),
            ], emoji="🎨")

            return screenshot

    except Exception as e:
        logger.error_tree("TempVoice Guide Render Failed", e, [
            ("Title", title),
        ])
        if page:
            try:
                await _return_page(page)
            except Exception:
                pass
        return None
