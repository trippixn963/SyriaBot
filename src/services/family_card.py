"""
SyriaBot - Family Card Generator
=================================

HTML/CSS based family tree card rendered with Playwright.
Reuses the browser pool from the rank card system.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import io
import time
from typing import Optional
from dataclasses import dataclass, field

import discord

from src.core.logger import logger
from src.services.xp.card import (
    _get_page, _return_page, get_render_semaphore,
)


# Cache: {user_id: (bytes, timestamp)}
_family_cache: dict = {}
_CACHE_TTL = 15


@dataclass
class FamilyMember:
    """A family member's display info."""
    user_id: int
    display_name: str
    avatar_url: str


@dataclass
class FamilyData:
    """All data needed to render a family card."""
    # Target user
    display_name: str
    username: str
    avatar_url: str
    # Family members
    spouse: Optional[FamilyMember] = None
    married_at: Optional[int] = None
    parents: list[FamilyMember] = field(default_factory=list)
    adopted_at: Optional[int] = None
    children: list[FamilyMember] = field(default_factory=list)
    siblings: list[FamilyMember] = field(default_factory=list)
    max_children: int = 5


def _fmt_date(timestamp: Optional[int]) -> str:
    """Format a unix timestamp as a short date string."""
    if not timestamp:
        return ""
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt.strftime("%b %d, %Y")


def _escape(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _member_circle(member: FamilyMember, size: int = 48) -> str:
    """Generate HTML for a small member avatar circle with name."""
    name = _escape(member.display_name[:14])
    return f'''<div class="member-item">
            <img class="member-avatar" src="{member.avatar_url}" width="{size}" height="{size}"
                 onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
            <div class="member-avatar-fallback" style="display:none;width:{size}px;height:{size}px">
                {_escape(member.display_name[0].upper())}
            </div>
            <span class="member-name">{name}</span>
        </div>'''


def _generate_family_html(data: FamilyData) -> str:
    """Generate HTML for the family tree card."""

    sections: list[str] = []

    # --- Parents section ---
    if data.parents:
        parent_items = ""
        for i, p in enumerate(data.parents):
            parent_items += _member_circle(p, 48)
            if i == 0 and len(data.parents) > 1:
                parent_items += '<div class="connector-amp">&</div>'

        date_str = _fmt_date(data.adopted_at)
        date_html = f'<span class="label-date">· adopted {date_str}</span>' if date_str else ""

        sections.append(f'''
        <div class="section">
            <div class="section-header"><span class="section-label">Parents</span>{date_html}</div>
            <div class="members-row">{parent_items}</div>
        </div>''')

    # --- Spouse section ---
    if data.spouse:
        date_str = _fmt_date(data.married_at)
        date_html = f'<span class="label-date">· married {date_str}</span>' if date_str else ""
        sections.append(f'''
        <div class="section">
            <div class="section-header"><span class="section-label">Spouse</span>{date_html}</div>
            <div class="spouse-row">
                <img class="spouse-avatar" src="{data.spouse.avatar_url}" width="50" height="50"
                     onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
                <div class="member-avatar-fallback spouse-fb" style="display:none;width:50px;height:50px">
                    {_escape(data.spouse.display_name[0].upper())}
                </div>
                <div class="spouse-name">{_escape(data.spouse.display_name[:20])}</div>
            </div>
        </div>''')

    # --- Children section ---
    if data.children:
        child_items = "".join(_member_circle(c, 46) for c in data.children[:5])
        sections.append(f'''
        <div class="section">
            <div class="section-header"><span class="section-label">Children ({len(data.children)}/{data.max_children})</span></div>
            <div class="members-grid">{child_items}</div>
        </div>''')

    # --- Siblings section ---
    if data.siblings:
        sib_items = "".join(_member_circle(s, 42) for s in data.siblings[:8])
        sections.append(f'''
        <div class="section">
            <div class="section-header"><span class="section-label">Siblings ({len(data.siblings)})</span></div>
            <div class="members-grid">{sib_items}</div>
        </div>''')

    # --- Empty state ---
    if not sections:
        sections.append('''
        <div class="empty-state">
            <div class="empty-icon">👪</div>
            <div class="empty-text">No family yet</div>
            <div class="empty-hint">Use marry, adopt, or get adopted to start your family!</div>
        </div>''')

    sections_html = "\n".join(sections)
    display_name_escaped = _escape(data.display_name[:20])
    username_escaped = _escape(data.username)

    html = f'''<!DOCTYPE html>
<html>
<head>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, 'Noto Sans', Ubuntu, sans-serif;
    background: transparent;
    display: flex;
    justify-content: center;
    padding: 10px;
}}

/* === Card border gradient === */
.card-outer {{
    padding: 2px;
    background: linear-gradient(140deg, #1F5E2E 0%, #2d8a42 35%, #E6B84A 70%, #c49a30 100%);
    border-radius: 18px;
    box-shadow: 0 6px 28px rgba(0,0,0,0.55), 0 0 30px rgba(31,94,46,0.2);
}}

/* === Main card === */
.card {{
    width: 480px;
    background: #111118;
    border-radius: 16px;
    overflow: hidden;
}}

/* === Header === */
.header {{
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 22px 22px 18px;
    background: linear-gradient(165deg, rgba(31,94,46,0.12) 0%, transparent 60%);
}}

.avatar-wrap {{
    position: relative;
    flex-shrink: 0;
    width: 72px;
    height: 72px;
}}

.avatar-ring {{
    position: absolute;
    inset: -3px;
    border-radius: 50%;
    background: linear-gradient(135deg, #1F5E2E, #E6B84A);
    z-index: 0;
}}

.avatar-ring-inner {{
    position: absolute;
    inset: 0;
    border-radius: 50%;
    border: 3px solid #111118;
    z-index: 1;
}}

.avatar-img {{
    width: 72px;
    height: 72px;
    border-radius: 50%;
    object-fit: cover;
    position: relative;
    z-index: 2;
}}

.avatar-fb {{
    width: 72px;
    height: 72px;
    border-radius: 50%;
    background: #1a1a24;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    color: #fff;
    font-weight: 700;
    position: relative;
    z-index: 2;
}}

.user-info {{
    flex: 1;
    min-width: 0;
}}

.display-name {{
    font-size: 22px;
    font-weight: 700;
    color: #fff;
    line-height: 1.25;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.username {{
    font-size: 13px;
    font-weight: 500;
    color: #555564;
    margin-top: 2px;
}}

.badge {{
    display: inline-block;
    margin-top: 6px;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #E6B84A;
    background: rgba(230,184,74,0.1);
    border: 1px solid rgba(230,184,74,0.2);
}}

/* === Section divider === */
.divider {{
    height: 1px;
    margin: 0 22px;
    background: linear-gradient(90deg, rgba(31,94,46,0.35), rgba(230,184,74,0.15), transparent);
}}

/* === Sections === */
.section {{
    padding: 14px 22px;
}}

.section + .section {{
    padding-top: 0;
}}

.section-header {{
    display: flex;
    align-items: baseline;
    gap: 6px;
    margin-bottom: 10px;
}}

.section-label {{
    font-size: 10px;
    font-weight: 700;
    color: #E6B84A;
    text-transform: uppercase;
    letter-spacing: 1.2px;
}}

.label-date {{
    font-size: 10px;
    font-weight: 500;
    color: #444454;
}}

/* === Spouse row === */
.spouse-row {{
    display: flex;
    align-items: center;
    gap: 12px;
}}

.spouse-avatar {{
    width: 50px;
    height: 50px;
    border-radius: 50%;
    object-fit: cover;
    border: 2px solid rgba(230,184,74,0.4);
    flex-shrink: 0;
}}

.spouse-fb {{
    border-radius: 50%;
    background: #1a1a24;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    color: #fff;
    font-weight: 700;
    border: 2px solid rgba(230,184,74,0.4);
    flex-shrink: 0;
}}

.spouse-name {{
    font-size: 15px;
    font-weight: 600;
    color: #ddd;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

/* === Members grid (children/siblings) === */
.members-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(60px, 1fr));
    gap: 10px 12px;
}}

.members-row {{
    display: flex;
    gap: 10px;
    align-items: flex-start;
}}

.member-item {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    width: 60px;
}}

.member-avatar {{
    border-radius: 50%;
    object-fit: cover;
    border: 2px solid rgba(31,94,46,0.3);
    flex-shrink: 0;
}}

.member-avatar-fallback {{
    border-radius: 50%;
    background: #1a1a24;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    color: #fff;
    font-weight: 700;
    border: 2px solid rgba(31,94,46,0.3);
}}

.member-name {{
    font-size: 10px;
    font-weight: 500;
    color: #666678;
    width: 60px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-align: center;
    line-height: 1.2;
}}

.connector-amp {{
    display: flex;
    align-items: center;
    color: #444454;
    font-size: 14px;
    font-weight: 600;
    padding: 0 2px;
}}

/* === Empty state === */
.empty-state {{
    text-align: center;
    padding: 28px 22px;
}}

.empty-icon {{
    font-size: 28px;
    margin-bottom: 6px;
}}

.empty-text {{
    font-size: 14px;
    font-weight: 600;
    color: #666678;
}}

.empty-hint {{
    font-size: 11px;
    color: #444454;
    margin-top: 3px;
}}

/* === Bottom spacer === */
.bottom-pad {{
    height: 8px;
}}
</style>
</head>
<body>
<div class="card-outer">
<div class="card">
    <div class="header">
        <div class="avatar-wrap">
            <div class="avatar-ring"></div>
            <div class="avatar-ring-inner"></div>
            <img class="avatar-img" src="{data.avatar_url}" width="72" height="72"
                 onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
            <div class="avatar-fb" style="display:none">
                {_escape(data.display_name[0].upper())}
            </div>
        </div>
        <div class="user-info">
            <div class="display-name">{display_name_escaped}</div>
            <div class="username">@{username_escaped}</div>
            <div class="badge">Family Tree</div>
        </div>
    </div>
    <div class="divider"></div>
    {sections_html}
    <div class="bottom-pad"></div>
</div>
</div>
</body>
</html>'''
    return html


async def generate_family_card(data: FamilyData) -> bytes:
    """Generate a family tree card image using Playwright."""
    global _family_cache

    # Check cache
    now = time.time()
    cache_key = data.username  # Unique per user (display_name can collide)
    if cache_key in _family_cache:
        cached_bytes, cached_time = _family_cache[cache_key]
        if now - cached_time < _CACHE_TTL:
            return cached_bytes

    # Evict expired entries
    expired = [k for k, (_, ts) in _family_cache.items() if now - ts >= _CACHE_TTL]
    for k in expired:
        del _family_cache[k]

    # Calculate needed height based on content
    height = 140  # header + divider + bottom pad
    if data.parents:
        height += 85
    if data.spouse:
        height += 80
    if data.children:
        cols = 480 // 72  # ~6 per row with grid
        rows = (len(data.children) + cols - 1) // cols
        height += 40 + rows * 68
    if data.siblings:
        cols = 480 // 72
        rows = (len(data.siblings) + cols - 1) // cols
        height += 40 + rows * 64
    if not data.spouse and not data.parents and not data.children and not data.siblings:
        height += 100

    async with get_render_semaphore():
        page = None
        try:
            page = await _get_page()
            await page.goto('about:blank')
            await page.set_viewport_size({'width': 520, 'height': max(height, 280)})

            html = _generate_family_html(data)
            await page.set_content(html, wait_until='networkidle')

            # Wait briefly for avatars to load
            try:
                await page.wait_for_timeout(800)
            except Exception:
                pass

            # Get actual card height from DOM
            actual_height = await page.evaluate('''() => {
                const wrapper = document.querySelector('.card-outer');
                return wrapper ? wrapper.getBoundingClientRect().height + 20 : 350;
            }''')

            # Resize viewport to actual content height
            await page.set_viewport_size({'width': 520, 'height': int(actual_height) + 20})

            screenshot = await page.screenshot(type='png', omit_background=True)

            await _return_page(page)
            page = None

            _family_cache[cache_key] = (screenshot, now)

            logger.tree("Family Card Generated", [
                ("User", data.display_name),
                ("Height", str(int(actual_height))),
            ], emoji="🎨")

            return screenshot

        except Exception as e:
            logger.error_tree("Family Card Failed", e, [
                ("User", data.display_name),
            ])
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            raise


async def resolve_family_member(guild: discord.Guild, user_id: int) -> FamilyMember:
    """Resolve a user ID to a FamilyMember with avatar URL."""
    member = guild.get_member(user_id)
    if member:
        return FamilyMember(
            user_id=user_id,
            display_name=member.display_name,
            avatar_url=str(member.display_avatar.replace(size=128, format="png")),
        )

    # Fallback: try to fetch user
    try:
        user = await guild.fetch_member(user_id)
        return FamilyMember(
            user_id=user_id,
            display_name=user.display_name,
            avatar_url=str(user.display_avatar.replace(size=128, format="png")),
        )
    except Exception as e:
        logger.error_tree("Family Member Fetch Failed", e, [
            ("User ID", str(user_id)),
            ("Guild", guild.name),
        ])

    # Last resort: default avatar
    return FamilyMember(
        user_id=user_id,
        display_name=f"User {user_id}",
        avatar_url="https://cdn.discordapp.com/embed/avatars/0.png",
    )
