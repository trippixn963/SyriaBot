"""
SyriaBot - Roulette Graphics
============================

Playwright-based roulette wheel renderer with elite graphics.
Matches the rank card visual style.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import math
from typing import List, Tuple, Optional
from dataclasses import dataclass

from src.core.logger import logger


# Reuse the rank card's browser infrastructure
from src.services.xp.card import (
    _get_page,
    _return_page,
    get_render_semaphore,
)


# Wheel colors - Syria theme (gold and green)
WHEEL_COLORS = [
    "#E6B84A",  # Syria Gold
    "#1F5E2E",  # Syria Green
    "#D4A73A",  # Gold darker
    "#2A7A3D",  # Green lighter
    "#C9982F",  # Gold variant
    "#245C32",  # Green variant
    "#E0C060",  # Gold light
    "#1A4D25",  # Green dark
]


@dataclass
class RoulettePlayer:
    """Player in the roulette game."""
    user_id: int
    display_name: str
    avatar_url: str


def _generate_wheel_html(
    players: List[RoulettePlayer],
    winner_index: Optional[int] = None,
    spin_degrees: float = 0,
    is_spinning: bool = False,
    show_winner: bool = False,
) -> str:
    """
    Generate HTML for the roulette wheel.

    Args:
        players: List of players in the game
        winner_index: Index of winning player (for final reveal)
        spin_degrees: Current rotation in degrees
        is_spinning: Whether wheel is currently spinning
        show_winner: Whether to highlight the winner
    """
    num_players = len(players)
    if num_players == 0:
        return ""

    slice_angle = 360 / num_players

    # Generate conic gradient for wheel segments
    gradient_stops = []
    for i in range(num_players):
        color = WHEEL_COLORS[i % len(WHEEL_COLORS)]
        start_angle = i * slice_angle
        end_angle = (i + 1) * slice_angle
        gradient_stops.append(f"{color} {start_angle}deg {end_angle}deg")

    conic_gradient = f"conic-gradient(from 0deg, {', '.join(gradient_stops)})"

    # Generate divider lines between segments
    dividers_html = ""
    for i in range(num_players):
        rotation = i * slice_angle
        dividers_html += f'''
            <div class="divider" style="transform: rotate({rotation}deg);"></div>
        '''

    # Generate player avatars positioned on the wheel
    avatars_html = ""
    avatar_size = 36  # Smaller avatars
    avatar_radius = 130  # Distance from center

    for i, player in enumerate(players):
        color = WHEEL_COLORS[i % len(WHEEL_COLORS)]
        # Position avatar at center of slice
        avatar_angle = i * slice_angle + (slice_angle / 2)
        avatar_x = 192 + avatar_radius * math.sin(math.radians(avatar_angle))
        avatar_y = 192 - avatar_radius * math.cos(math.radians(avatar_angle))

        # Highlight winner
        is_winner = show_winner and winner_index == i
        winner_glow = f"box-shadow: 0 0 20px #fff, 0 0 40px {color}, 0 0 60px {color};" if is_winner else ""
        winner_scale = "transform: scale(1.3);" if is_winner else ""
        winner_border = "4px solid #fff" if is_winner else f"3px solid rgba(0,0,0,0.4)"

        # Get first letter for fallback
        initial = player.display_name[0].upper() if player.display_name else "?"

        avatars_html += f'''
            <div class="player-avatar" style="
                left: {avatar_x - avatar_size/2}px;
                top: {avatar_y - avatar_size/2}px;
                width: {avatar_size}px;
                height: {avatar_size}px;
                border: {winner_border};
                {winner_glow}
                {winner_scale}
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

    # Winner announcement
    winner_html = ""
    if show_winner and winner_index is not None:
        winner = players[winner_index]
        winner_html = f'''
            <div class="winner-banner">
                <span class="winner-icon">🎉</span>
                <span class="winner-name">{winner.display_name[:12]}</span>
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
            width: 480px;
            height: 540px;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #0f0f1a 100%);
            border-radius: 20px;
            position: relative;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
        }}

        .title {{
            font-size: 36px;
            font-weight: 900;
            letter-spacing: 4px;
            background: linear-gradient(135deg, #E6B84A 0%, #1F5E2E 50%, #E6B84A 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 12px;
            text-transform: uppercase;
        }}

        .wheel-container {{
            width: 420px;
            height: 420px;
            position: relative;
            display: flex;
            justify-content: center;
            align-items: center;
        }}

        /* Outer ring glow */
        .wheel-glow {{
            position: absolute;
            width: 400px;
            height: 400px;
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
            width: 396px;
            height: 396px;
            border-radius: 50%;
            background: linear-gradient(145deg, #2a2a4a, #1a1a2e);
            box-shadow:
                0 0 0 4px rgba(230, 184, 74, 0.4),
                0 0 30px rgba(230, 184, 74, 0.2),
                inset 0 0 30px rgba(0,0,0,0.5);
        }}

        /* The wheel itself */
        .wheel-base {{
            width: 384px;
            height: 384px;
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
            width: 3px;
            height: 50%;
            background: linear-gradient(to bottom,
                rgba(0,0,0,0.6) 0%,
                rgba(0,0,0,0.4) 30%,
                rgba(0,0,0,0.2) 60%,
                transparent 100%);
            transform-origin: bottom center;
            margin-left: -1.5px;
        }}

        /* Inner shadow overlay for depth */
        .wheel-inner-shadow {{
            position: absolute;
            inset: 0;
            border-radius: 50%;
            background: radial-gradient(circle at center,
                transparent 0%,
                transparent 40%,
                rgba(0,0,0,0.1) 70%,
                rgba(0,0,0,0.3) 100%);
            pointer-events: none;
        }}

        /* Player avatars */
        .player-avatar {{
            position: absolute;
            border-radius: 50%;
            overflow: hidden;
            z-index: 10;
            background: linear-gradient(135deg, #3a3a4a, #2a2a3a);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
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
            font-size: 16px;
            font-weight: 700;
            color: #fff;
        }}

        /* Center hub */
        .center-hub {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 70px;
            height: 70px;
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
        }}

        .center-hub span {{
            font-size: 28px;
        }}

        /* Pointer arrow */
        .pointer {{
            position: absolute;
            top: 2px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 50;
            filter: drop-shadow(0 4px 8px rgba(0,0,0,0.5));
        }}

        .pointer-outer {{
            width: 0;
            height: 0;
            border-left: 18px solid transparent;
            border-right: 18px solid transparent;
            border-top: 35px solid #fff;
        }}

        .pointer-inner {{
            position: absolute;
            top: 3px;
            left: 50%;
            transform: translateX(-50%);
            width: 0;
            height: 0;
            border-left: 12px solid transparent;
            border-right: 12px solid transparent;
            border-top: 24px solid #E6B84A;
        }}

        /* Winner banner */
        .winner-banner {{
            position: absolute;
            bottom: 15px;
            left: 50%;
            transform: translateX(-50%);
            background: linear-gradient(145deg, #1F5E2E, #2A7A3D);
            padding: 10px 28px;
            border-radius: 25px;
            display: flex;
            align-items: center;
            gap: 8px;
            box-shadow:
                0 4px 20px rgba(31, 94, 46, 0.5),
                0 0 40px rgba(31, 94, 46, 0.3);
            z-index: 100;
            border: 2px solid #E6B84A;
        }}

        .winner-icon {{
            font-size: 24px;
        }}

        .winner-name {{
            font-size: 20px;
            font-weight: 800;
            color: #fff;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }}

        .winner-text {{
            font-size: 18px;
            font-weight: 700;
            color: rgba(255,255,255,0.9);
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
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
                    <span>🎰</span>
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
) -> bytes:
    """
    Generate a static wheel image showing all players.
    Used for the initial "join" phase.
    """
    async with get_render_semaphore():
        page = None
        try:
            page = await _get_page()
            await page.goto('about:blank')
            await page.set_viewport_size({'width': 500, 'height': 560})

            html = _generate_wheel_html(players, is_spinning=False)
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
) -> bytes:
    """
    Generate the final wheel image with winner highlighted.
    The wheel is rotated so the winner is at the top (under pointer).
    """
    num_players = len(players)
    if num_players == 0:
        raise ValueError("No players")

    slice_angle = 360 / num_players

    # Calculate rotation to put winner under pointer (top)
    # Winner should be at 0 degrees (top), so we rotate to position them there
    # Pointer is at top, so winner slice center should be at 0 degrees
    winner_center_angle = winner_index * slice_angle + (slice_angle / 2)
    # Rotate so winner is at top: we need to subtract winner's angle from 360
    # Plus add some extra rotations for visual effect
    spin_degrees = (360 * 5) + (360 - winner_center_angle)

    async with get_render_semaphore():
        page = None
        try:
            page = await _get_page()
            await page.goto('about:blank')
            await page.set_viewport_size({'width': 500, 'height': 560})

            html = _generate_wheel_html(
                players,
                winner_index=winner_index,
                spin_degrees=spin_degrees,
                is_spinning=False,
                show_winner=True,
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


async def generate_spin_frames(
    players: List[RoulettePlayer],
    winner_index: int,
    num_frames: int = 8,
) -> List[bytes]:
    """
    Generate multiple frames for animated spin effect.
    Each frame shows progressive rotation.

    Returns list of PNG bytes for each frame.
    """
    num_players = len(players)
    if num_players == 0:
        raise ValueError("No players")

    slice_angle = 360 / num_players

    # Calculate final rotation
    winner_center_angle = winner_index * slice_angle + (slice_angle / 2)
    final_degrees = (360 * 5) + (360 - winner_center_angle)

    frames = []

    async with get_render_semaphore():
        page = None
        try:
            page = await _get_page()
            await page.goto('about:blank')
            await page.set_viewport_size({'width': 500, 'height': 560})

            for i in range(num_frames):
                # Easing function (deceleration)
                progress = (i + 1) / num_frames
                eased_progress = 1 - (1 - progress) ** 3  # Cubic ease-out
                current_degrees = final_degrees * eased_progress

                # Only show winner on last frame
                show_winner = (i == num_frames - 1)

                html = _generate_wheel_html(
                    players,
                    winner_index=winner_index if show_winner else None,
                    spin_degrees=current_degrees,
                    is_spinning=False,
                    show_winner=show_winner,
                )

                await page.set_content(html, wait_until='domcontentloaded')

                screenshot = await page.screenshot(type='png', omit_background=True)
                frames.append(screenshot)

            await _return_page(page)
            page = None

            logger.tree("Roulette Spin Frames Generated", [
                ("Players", str(num_players)),
                ("Frames", str(num_frames)),
                ("Winner", players[winner_index].display_name),
            ], emoji="🎬")

            return frames

        except Exception as e:
            logger.tree("Roulette Frames Failed", [
                ("Error", str(e)[:100]),
            ], emoji="❌")
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            raise
