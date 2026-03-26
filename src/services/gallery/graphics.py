"""
SyriaBot - Gallery Guide Graphics
==================================

CSS-rendered guide image for gallery media channel posts.
Same gold/green style as TempVoice guides.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from src.core.logger import logger
from src.services.xp.card import _get_page, _return_page, get_render_semaphore


GALLERY_ITEMS = [
    ("❤️ REACT", "Show love with a heart reaction"),
    ("💬 COMMENT", "Share your thoughts below"),
    ("📷 SHARE", "Post your best photos and videos"),
    ("🏷️ TAG", "Use tags to categorize your post"),
    ("🤝 RESPECT", "Keep it clean and respectful"),
    ("🚫 NO SPAM", "Quality over quantity"),
]


def _build_gallery_html() -> str:
    """Build HTML for gallery guide image."""

    cards_html = ""
    for name, desc in GALLERY_ITEMS:
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
    <div class="title">Gallery</div>
    <div class="subtitle">Share your moments with the community</div>
    <div class="green-line"></div>
    <div class="grid">
        {cards_html}
    </div>
</body>
</html>"""


async def render_gallery_guide() -> bytes | None:
    """Render the gallery guide image using Playwright."""
    async with get_render_semaphore():
        page = None
        try:
            page = await _get_page()
            html = _build_gallery_html()
            await page.set_content(html, wait_until='domcontentloaded')

            body = await page.query_selector('body')
            screenshot = await body.screenshot(type='png', omit_background=True)

            await _return_page(page)
            page = None

            logger.tree("Gallery Guide Rendered", [
                ("Cards", str(len(GALLERY_ITEMS))),
            ], emoji="🎨")

            return screenshot
        except Exception as e:
            logger.error_tree("Gallery Guide Render Failed", e)
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            return None
