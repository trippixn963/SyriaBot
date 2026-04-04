"""
SyriaBot - TempVoice Guide Graphics
====================================

CSS-rendered guide images for voice controls and music commands.
Dark background matching Discord's embed — seamless integration.
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
    ("LOCK", "Lock / unlock (Level 20+)", "1455709111684694107"),
    ("LIMIT", "Set user limit", "1455709299732123762"),
    ("RENAME", "Rename channel (boosters only)", "1455709387711578394"),
    ("ALLOW", "Add trusted users", "1455709499792031744"),
    ("BLOCK", "Block users", "1455709662316986539"),
    ("KICK", "Kick from channel", "1455709879976198361"),
    ("CLAIM", "Claim ownerless channel", "1455709985467011173"),
    ("TRANSFER", "Transfer ownership", "1455710226429902858"),
    ("CLEAR", "Clear chat messages", "1455710362539397192"),
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
# HTML Template — dark background, matches Discord embed
# =============================================================================

# Discord embed background color
_DISCORD_EMBED_BG = "#2b2d31"

# Number of columns for each guide type
_VOICE_COLS = 3
_MUSIC_COLS = 3


def _build_guide_html(title: str, subtitle: str, items: list[tuple], cols: int = 3) -> str:
    """Build HTML for a guide image — dark bg matching Discord, gold accents, compact grid.

    Items can be 2-tuples (name, desc) or 3-tuples (name, desc, emoji_id).
    When emoji_id is provided, the Discord CDN emoji is rendered beside the name.
    """

    cards_html = ""
    for item in items:
        name, desc = item[0], item[1]
        emoji_id = item[2] if len(item) > 2 else None

        icon_html = ""
        if emoji_id:
            icon_html = f'<img class="card-icon" src="https://cdn.discordapp.com/emojis/{emoji_id}.webp?size=48" />'

        cards_html += f"""
            <div class="card">
                <div class="card-header">
                    {icon_html}
                    <div class="card-name">{name}</div>
                </div>
                <div class="card-desc">{desc}</div>
            </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
<style>
    @font-face {{ font-family: 'Inter'; src: url('file:///usr/share/fonts/truetype/inter/Inter-Regular.ttf'); font-weight: 400; }}
    @font-face {{ font-family: 'Inter'; src: url('file:///usr/share/fonts/truetype/inter/Inter-SemiBold.ttf'); font-weight: 600; }}
    @font-face {{ font-family: 'Inter'; src: url('file:///usr/share/fonts/truetype/inter/Inter-Bold.ttf'); font-weight: 700; }}
    @font-face {{ font-family: 'Inter'; src: url('file:///usr/share/fonts/truetype/inter/Inter-ExtraBold.ttf'); font-weight: 800; }}

    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
        background: transparent;
        font-family: 'Inter', sans-serif;
        width: 800px;
        padding: {"28px 20px 24px" if title else "12px 20px 16px"};
    }}

    .title {{
        text-align: center;
        font-family: 'Inter', sans-serif;
        font-weight: 800;
        font-size: 28px;
        letter-spacing: 1px;
        color: #D4AF37;
        margin-bottom: 6px;
    }}

    .subtitle {{
        text-align: center;
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        font-size: 12px;
        letter-spacing: 3px;
        text-transform: uppercase;
        color: #5a5d63;
        margin-bottom: 18px;
    }}

    .grid {{
        display: grid;
        grid-template-columns: repeat({cols}, 1fr);
        gap: 8px;
    }}

    .card {{
        background: #1e1f22;
        border: 1px solid rgba(212, 175, 55, 0.20);
        border-radius: 10px;
        padding: 14px 16px;
    }}

    .card-header {{
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 4px;
    }}

    .card-icon {{
        width: 22px;
        height: 22px;
        flex-shrink: 0;
    }}

    .card-name {{
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        font-size: 16px;
        letter-spacing: 0.5px;
        color: #D4AF37;
    }}

    .card-desc {{
        font-family: 'Inter', sans-serif;
        font-weight: 400;
        font-size: 13px;
        color: #8b8d93;
        line-height: 1.3;
    }}
</style>
</head>
<body>
    {"" if not title else f'<div class="title">{title}</div>'}
    {"" if not subtitle else f'<div class="subtitle">{subtitle}</div>'}
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
    return await _render_guide("", "", VOICE_CONTROLS, cols=_VOICE_COLS)


async def render_music_guide() -> bytes | None:
    """Render the music commands guide image."""
    return await _render_guide("Music Commands", "Boogie Premium", MUSIC_COMMANDS, cols=_MUSIC_COLS)


async def _render_guide(
    title: str, subtitle: str, items: list[tuple], cols: int = 3,
) -> bytes | None:
    """Render a guide to PNG bytes with Discord-matching dark background."""
    semaphore = get_render_semaphore()
    page = None

    try:
        async with semaphore:
            page = await _get_page()
            await page.goto('about:blank')

            rows = (len(items) + cols - 1) // cols
            has_title = bool(title)
            height = (80 if has_title else 36) + rows * 82

            await page.set_viewport_size({'width': 800, 'height': height})

            html = _build_guide_html(title, subtitle, items, cols)
            await page.set_content(html, wait_until='networkidle')

            try:
                await page.wait_for_timeout(400)
            except Exception:
                pass

            screenshot = await page.screenshot(type='png', omit_background=True)

            await _return_page(page)
            page = None

            logger.tree("TempVoice Guide Rendered", [
                ("Title", title or "(voice controls)"),
                ("Cards", str(len(items))),
                ("Layout", f"{cols}x{rows}"),
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
