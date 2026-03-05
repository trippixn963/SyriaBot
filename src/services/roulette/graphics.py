"""
SyriaBot - Roulette Graphics
============================

Playwright-based roulette wheel renderer with elite graphics.
Matches the rank card visual style.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import math
from typing import List, Optional
from dataclasses import dataclass

from src.core.logger import logger


# Reuse the rank card's browser infrastructure
from src.services.xp.card import (
    _get_page,
    _return_page,
    get_render_semaphore,
)


# Wheel geometry
WHEEL_SIZE = 396  # px — must match .wheel-base width/height in CSS
WHEEL_CENTER = WHEEL_SIZE // 2  # 198

# Strict alternating gold/green — never two similar colors adjacent
WHEEL_COLOR_GOLD = "#D4A73A"
WHEEL_COLOR_GREEN = "#1F5E2E"


@dataclass
class RoulettePlayer:
    """Player in the roulette game."""
    user_id: int
    display_name: str
    avatar_url: str
    weight: float = 0.0  # Proportion of total (0.0-1.0)
    message_count: int = 0


def _get_segment_color(index: int) -> str:
    """Alternate gold/green strictly by index."""
    return WHEEL_COLOR_GOLD if index % 2 == 0 else WHEEL_COLOR_GREEN


def _generate_wheel_html(
    players: List[RoulettePlayer],
    winner_index: Optional[int] = None,
    spin_degrees: float = 0,
    is_spinning: bool = False,
    show_winner: bool = False,
    guild_icon_url: Optional[str] = None,
) -> str:
    """
    Generate HTML for the roulette wheel with weighted segments.

    Each player's segment size is proportional to their weight.
    """
    num_players = len(players)
    if num_players == 0:
        return ""

    # Build cumulative angles from weights
    cumulative_angles = []
    current_angle = 0.0
    for player in players:
        start = current_angle
        extent = player.weight * 360
        end = start + extent
        cumulative_angles.append((start, end))
        current_angle = end

    # Generate conic gradient for wheel segments (strict alternating)
    gradient_stops = []
    for i, (start, end) in enumerate(cumulative_angles):
        color = _get_segment_color(i)
        gradient_stops.append(f"{color} {start:.2f}deg {end:.2f}deg")

    conic_gradient = f"conic-gradient(from 0deg, {', '.join(gradient_stops)})"

    # Generate divider lines between segments
    dividers_html = ""
    for i, (start, _end) in enumerate(cumulative_angles):
        dividers_html += f'''
            <div class="divider" style="transform: rotate({start:.2f}deg);"></div>
        '''

    # Generate player avatars positioned on the wheel
    avatars_html = ""
    avatar_size = 56
    avatar_radius = 130

    for i, player in enumerate(players):
        color = _get_segment_color(i)
        start, end = cumulative_angles[i]
        slice_angle = end - start

        # Scale avatar size based on slice — smaller slices get slightly smaller avatars
        # but never below 40px
        scaled_size = avatar_size
        if slice_angle < 25:
            scaled_size = max(40, int(avatar_size * (slice_angle / 36)))

        # Position avatar at center of this player's slice
        avatar_angle = (start + end) / 2
        avatar_x = WHEEL_CENTER + avatar_radius * math.sin(math.radians(avatar_angle))
        avatar_y = WHEEL_CENTER - avatar_radius * math.cos(math.radians(avatar_angle))

        # Highlight winner
        is_winner = show_winner and winner_index == i
        if is_winner:
            border = "4px solid #fff"
            glow = "box-shadow: 0 0 15px #fff, 0 0 30px #E6B84A, 0 0 50px #E6B84A;"
            scale = "transform: scale(1.35);"
        else:
            border = "3px solid rgba(255,255,255,0.25)"
            glow = "box-shadow: 0 2px 8px rgba(0,0,0,0.6);"
            scale = ""

        # Get first letter for fallback
        initial = player.display_name[0].upper() if player.display_name else "?"

        avatars_html += f'''
            <div class="player-avatar" style="
                left: {avatar_x - scaled_size/2}px;
                top: {avatar_y - scaled_size/2}px;
                width: {scaled_size}px;
                height: {scaled_size}px;
                border: {border};
                {glow}
                {scale}
            ">
                <img src="{player.avatar_url}"
                     onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                <div class="avatar-fallback" style="display:none;">{initial}</div>
            </div>
        '''

    # Spin animation CSS
    spin_css = ""
    if is_spinning:
        spin_css = f'''
            @keyframes spin {{
                from {{ transform: rotate(0deg); }}
                to {{ transform: rotate({spin_degrees}deg); }}
            }}
            .wheel-rotator {{
                animation: spin 4s cubic-bezier(0.17, 0.67, 0.12, 0.99) forwards;
            }}
        '''
    else:
        spin_css = f'''
            .wheel-rotator {{
                transform: rotate({spin_degrees}deg);
            }}
        '''

    # Center hub content (guild icon or fallback emoji)
    if guild_icon_url:
        center_hub_content = f'<img src="{guild_icon_url}" onerror="this.style.display=\'none\'; this.nextElementSibling.style.display=\'flex\'"><span style="display:none;">🎰</span>'
    else:
        center_hub_content = '<span>🎰</span>'

    # Winner announcement
    winner_html = ""
    if show_winner and winner_index is not None:
        winner = players[winner_index]
        winner_html = f'''
            <div class="winner-banner">
                <span class="winner-icon">🎉</span>
                <span class="winner-name">{winner.display_name[:16]}</span>
                <span class="winner-text">WINS!</span>
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
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: transparent;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }}

        .card-wrapper {{
            padding: 4px;
            background: linear-gradient(135deg, #E6B84A, #1F5E2E, #E6B84A);
            border-radius: 24px;
            position: relative;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4), 0 0 60px rgba(230, 184, 74, 0.3);
        }}

        .card-wrapper::before {{
            content: '';
            position: absolute;
            inset: -8px;
            border-radius: 32px;
            background: linear-gradient(135deg, #E6B84A55, #1F5E2E55, #E6B84A55);
            filter: blur(20px);
            opacity: 0.8;
            z-index: -1;
        }}

        .card {{
            width: 500px;
            height: 570px;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #0f0f1a 100%);
            border-radius: 20px;
            position: relative;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 16px 20px;
        }}

        .title {{
            font-size: 36px;
            font-weight: 900;
            letter-spacing: 4px;
            background: linear-gradient(135deg, #E6B84A 0%, #F0D080 50%, #E6B84A 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
            text-transform: uppercase;
        }}

        .wheel-container {{
            width: 440px;
            height: 440px;
            position: relative;
            display: flex;
            justify-content: center;
            align-items: center;
        }}

        /* Outer ring glow */
        .wheel-glow {{
            position: absolute;
            width: 420px;
            height: 420px;
            border-radius: 50%;
            background: conic-gradient(from 0deg, #E6B84A66, #1F5E2E66, #E6B84A66, #1F5E2E66, #E6B84A66);
            filter: blur(15px);
            animation: glowRotate 8s linear infinite;
        }}

        @keyframes glowRotate {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(360deg); }}
        }}

        /* Outer decorative ring */
        .wheel-outer-ring {{
            position: absolute;
            width: 410px;
            height: 410px;
            border-radius: 50%;
            background: linear-gradient(145deg, #2a2a4a, #1a1a2e);
            box-shadow:
                0 0 0 4px rgba(230, 184, 74, 0.5),
                0 0 30px rgba(230, 184, 74, 0.2),
                inset 0 0 30px rgba(0,0,0,0.5);
        }}

        /* The wheel itself */
        .wheel-base {{
            width: 396px;
            height: 396px;
            border-radius: 50%;
            position: relative;
            overflow: hidden;
            box-shadow: inset 0 0 20px rgba(0,0,0,0.3);
        }}

        .wheel-rotator {{
            width: 100%;
            height: 100%;
            position: relative;
        }}

        /* Wheel segments using conic gradient */
        .wheel-segments {{
            width: 100%;
            height: 100%;
            border-radius: 50%;
            background: {conic_gradient};
            position: relative;
        }}

        /* Segment divider lines */
        .divider {{
            position: absolute;
            top: 0;
            left: 50%;
            width: 2px;
            height: 50%;
            background: linear-gradient(to bottom,
                rgba(255,255,255,0.5) 0%,
                rgba(255,255,255,0.3) 30%,
                rgba(255,255,255,0.1) 60%,
                transparent 100%);
            transform-origin: bottom center;
            margin-left: -1px;
        }}

        /* Inner shadow overlay for depth */
        .wheel-inner-shadow {{
            position: absolute;
            inset: 0;
            border-radius: 50%;
            background: radial-gradient(circle at center,
                transparent 0%,
                transparent 35%,
                rgba(0,0,0,0.08) 65%,
                rgba(0,0,0,0.25) 100%);
            pointer-events: none;
        }}

        /* Player avatars */
        .player-avatar {{
            position: absolute;
            border-radius: 50%;
            overflow: hidden;
            z-index: 10;
            background: linear-gradient(135deg, #3a3a4a, #2a2a3a);
        }}

        .player-avatar img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}

        .avatar-fallback {{
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            font-weight: 700;
            color: #fff;
        }}

        /* Center hub */
        .center-hub {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 64px;
            height: 64px;
            background: linear-gradient(145deg, #1a1a2e, #0f0f1a);
            border-radius: 50%;
            border: 4px solid #E6B84A;
            box-shadow:
                0 0 20px rgba(230, 184, 74, 0.5),
                inset 0 0 15px rgba(0,0,0,0.5);
            z-index: 30;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }}

        .center-hub img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 50%;
        }}

        .center-hub span {{
            font-size: 26px;
        }}

        /* Pointer arrow */
        .pointer {{
            position: absolute;
            top: 0px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 50;
            filter: drop-shadow(0 4px 10px rgba(0,0,0,0.7));
        }}

        .pointer-outer {{
            width: 0;
            height: 0;
            border-left: 20px solid transparent;
            border-right: 20px solid transparent;
            border-top: 38px solid #fff;
        }}

        .pointer-inner {{
            position: absolute;
            top: 3px;
            left: 50%;
            transform: translateX(-50%);
            width: 0;
            height: 0;
            border-left: 13px solid transparent;
            border-right: 13px solid transparent;
            border-top: 26px solid #E6B84A;
        }}

        /* Winner banner */
        .winner-banner {{
            position: absolute;
            bottom: 12px;
            left: 50%;
            transform: translateX(-50%);
            background: linear-gradient(145deg, #1F5E2E, #2A7A3D);
            padding: 12px 32px;
            border-radius: 25px;
            display: flex;
            align-items: center;
            gap: 10px;
            box-shadow:
                0 4px 20px rgba(31, 94, 46, 0.5),
                0 0 40px rgba(31, 94, 46, 0.3);
            z-index: 100;
            border: 2px solid #E6B84A;
            white-space: nowrap;
        }}

        .winner-icon {{
            font-size: 26px;
        }}

        .winner-name {{
            font-size: 22px;
            font-weight: 800;
            color: #fff;
            text-shadow: 0 2px 4px rgba(0,0,0,0.4);
        }}

        .winner-text {{
            font-size: 20px;
            font-weight: 700;
            color: rgba(255,255,255,0.9);
            text-shadow: 0 2px 4px rgba(0,0,0,0.4);
        }}

        {spin_css}
    </style>
</head>
<body>
    <div class="card-wrapper">
        <div class="card">
            <div class="title">Roulette</div>

            <div class="wheel-container">
                <!-- Glow effect -->
                <div class="wheel-glow"></div>

                <!-- Outer decorative ring -->
                <div class="wheel-outer-ring"></div>

                <!-- Pointer -->
                <div class="pointer">
                    <div class="pointer-outer"></div>
                    <div class="pointer-inner"></div>
                </div>

                <!-- Main wheel -->
                <div class="wheel-base">
                    <div class="wheel-rotator">
                        <div class="wheel-segments">
                            {dividers_html}
                        </div>
                        {avatars_html}
                        <div class="wheel-inner-shadow"></div>
                    </div>
                </div>

                <!-- Center hub -->
                <div class="center-hub">
                    {center_hub_content}
                </div>
            </div>

            {winner_html}
        </div>
    </div>
</body>
</html>
'''
    return html


async def generate_wheel_static(
    players: List[RoulettePlayer],
    title_text: str = "JOIN THE ROULETTE!",
    guild_icon_url: Optional[str] = None,
) -> bytes:
    """
    Generate a static wheel image showing all players.
    Used for the announcement phase.
    """
    async with get_render_semaphore():
        page = None
        try:
            page = await _get_page()
            await page.goto('about:blank')
            await page.set_viewport_size({'width': 520, 'height': 590})

            html = _generate_wheel_html(players, is_spinning=False, guild_icon_url=guild_icon_url)
            # Replace title
            html = html.replace(">Roulette<", f">{title_text}<")

            await page.set_content(html, wait_until='networkidle')

            # Wait for avatars
            try:
                await page.wait_for_timeout(500)
            except Exception:
                pass

            screenshot = await page.screenshot(type='png', omit_background=True)

            await _return_page(page)
            page = None

            logger.tree("Roulette Wheel Generated", [
                ("Players", str(len(players))),
                ("Type", "Static"),
            ], emoji="🎰")

            return screenshot

        except Exception as e:
            logger.tree("Roulette Wheel Failed", [
                ("Players", str(len(players))),
                ("Error", str(e)[:100]),
            ], emoji="❌")
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            raise


async def generate_wheel_result(
    players: List[RoulettePlayer],
    winner_index: int,
    guild_icon_url: Optional[str] = None,
) -> bytes:
    """
    Generate the final wheel image with winner highlighted.
    The wheel is rotated so the winner is at the top (under pointer).
    Uses weighted angles for segment sizes.
    """
    num_players = len(players)
    if num_players == 0:
        raise ValueError("No players")

    # Calculate the center angle of the winner's weighted slice
    cumulative = 0.0
    for i in range(winner_index):
        cumulative += players[i].weight * 360
    winner_slice_angle = players[winner_index].weight * 360
    winner_center_angle = cumulative + (winner_slice_angle / 2)

    # Rotate so winner is at top (under pointer)
    spin_degrees = (360 * 5) + (360 - winner_center_angle)

    async with get_render_semaphore():
        page = None
        try:
            page = await _get_page()
            await page.goto('about:blank')
            await page.set_viewport_size({'width': 520, 'height': 590})

            html = _generate_wheel_html(
                players,
                winner_index=winner_index,
                spin_degrees=spin_degrees,
                is_spinning=False,
                show_winner=True,
                guild_icon_url=guild_icon_url,
            )

            await page.set_content(html, wait_until='networkidle')

            # Wait for avatars
            try:
                await page.wait_for_timeout(500)
            except Exception:
                pass

            screenshot = await page.screenshot(type='png', omit_background=True)

            await _return_page(page)
            page = None

            logger.tree("Roulette Result Generated", [
                ("Players", str(num_players)),
                ("Winner", players[winner_index].display_name),
                ("Rotation", f"{spin_degrees:.0f}°"),
            ], emoji="🎉")

            return screenshot

        except Exception as e:
            logger.tree("Roulette Result Failed", [
                ("Error", str(e)[:100]),
            ], emoji="❌")
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            raise
