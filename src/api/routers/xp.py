"""
SyriaBot - XP Router
====================

XP modification endpoints (protected by API key).

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.core.logger import logger
from src.core.config import config
from src.services.database import db
from src.services.xp.utils import level_from_xp
from src.api.dependencies import require_api_key
from src.api.services.cache import get_cache_service
from src.api.services.websocket import get_ws_manager
from src.api.utils import get_client_ip


router = APIRouter(prefix="/api/syria/xp", tags=["XP"])


# =============================================================================
# Request Models
# =============================================================================

class XPGrantRequest(BaseModel):
    """Request body for granting XP."""

    user_id: int = Field(..., description="Discord user ID")
    amount: int = Field(..., ge=1, le=100000, description="XP amount to add (1-100000)")
    reason: str = Field(default="API grant", description="Reason for the grant (for logging)")


class XPSetRequest(BaseModel):
    """Request body for setting XP."""

    user_id: int = Field(..., description="Discord user ID")
    xp: int = Field(..., ge=0, le=10000000, description="New XP value (0-10000000)")
    reason: str = Field(default="API set", description="Reason for the change (for logging)")


# =============================================================================
# Response Models
# =============================================================================

class XPGrantResponse(BaseModel):
    """Response for XP grant operation."""

    success: bool = True
    user_id: int
    xp_added: int
    new_xp: int
    old_level: int
    new_level: int
    leveled_up: bool


class XPSetResponse(BaseModel):
    """Response for XP set operation."""

    success: bool = True
    user_id: int
    old_xp: int
    new_xp: int
    old_level: int
    new_level: int


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/grant", response_model=XPGrantResponse)
async def grant_xp(
    request: Request,
    body: XPGrantRequest,
    api_key: str = Depends(require_api_key),
) -> JSONResponse:
    """
    Grant XP to a user (additive).

    Requires X-API-Key header for authentication.

    Request Body:
    - user_id: Discord user ID
    - amount: XP to add (1-100000)
    - reason: Optional reason for logging
    """
    client_ip = get_client_ip(request)
    cache = get_cache_service()

    try:
        # Get current XP data
        guild_id = config.GUILD_ID
        user_data = await asyncio.to_thread(db.get_user_xp, body.user_id, guild_id)

        if not user_data:
            # Create new user entry
            user_data = await asyncio.to_thread(db.ensure_user_xp, body.user_id, guild_id)

        current_xp = user_data.get("xp", 0)
        current_level = user_data.get("level", 0)
        new_xp = current_xp + body.amount
        new_level = level_from_xp(new_xp)

        # Update XP in database
        await asyncio.to_thread(db.add_xp, body.user_id, guild_id, body.amount)

        logger.tree("XP Granted via API", [
            ("ID", str(body.user_id)),
            ("Amount", f"+{body.amount}"),
            ("New XP", str(new_xp)),
            ("Level", f"{current_level} -> {new_level}" if new_level != current_level else str(new_level)),
            ("Reason", body.reason[:50]),
            ("Client IP", client_ip),
        ], emoji="⬆️")

        # Clear response cache
        await cache.clear_responses()

        # Broadcast XP change to dashboard via WebSocket
        ws = get_ws_manager()
        await ws.increment_xp(body.amount)

        return JSONResponse(
            content=XPGrantResponse(
                success=True,
                user_id=body.user_id,
                xp_added=body.amount,
                new_xp=new_xp,
                old_level=current_level,
                new_level=new_level,
                leveled_up=new_level > current_level,
            ).model_dump()
        )

    except Exception as e:
        logger.error_tree("XP Grant API Error", e, [
            ("ID", str(body.user_id)),
            ("Amount", str(body.amount)),
            ("Client IP", client_ip),
        ])
        return JSONResponse(
            content={"error": "Internal server error"},
            status_code=500,
        )


@router.post("/set", response_model=XPSetResponse)
async def set_xp(
    request: Request,
    body: XPSetRequest,
    api_key: str = Depends(require_api_key),
) -> JSONResponse:
    """
    Set XP for a user (overwrites existing value).

    Requires X-API-Key header for authentication.

    Request Body:
    - user_id: Discord user ID
    - xp: New XP value (0-10000000)
    - reason: Optional reason for logging
    """
    client_ip = get_client_ip(request)
    cache = get_cache_service()

    try:
        guild_id = config.GUILD_ID
        user_data = await asyncio.to_thread(db.get_user_xp, body.user_id, guild_id)

        old_xp = 0
        old_level = 0
        if user_data:
            old_xp = user_data.get("xp", 0)
            old_level = user_data.get("level", 0)

        new_level = level_from_xp(body.xp)

        # Set XP in database
        await asyncio.to_thread(db.set_xp, body.user_id, guild_id, body.xp, new_level)

        logger.tree("XP Set via API", [
            ("ID", str(body.user_id)),
            ("XP", f"{old_xp} -> {body.xp}"),
            ("Level", f"{old_level} -> {new_level}"),
            ("Reason", body.reason[:50]),
            ("Client IP", client_ip),
        ], emoji="✏️")

        # Clear response cache
        await cache.clear_responses()

        return JSONResponse(
            content=XPSetResponse(
                success=True,
                user_id=body.user_id,
                old_xp=old_xp,
                new_xp=body.xp,
                old_level=old_level,
                new_level=new_level,
            ).model_dump()
        )

    except Exception as e:
        logger.error_tree("XP Set API Error", e, [
            ("ID", str(body.user_id)),
            ("XP", str(body.xp)),
            ("Client IP", client_ip),
        ])
        return JSONResponse(
            content={"error": "Internal server error"},
            status_code=500,
        )


__all__ = ["router"]


class XPDrainRequest(BaseModel):
    """Request body for draining XP."""

    user_id: int = Field(..., description="Discord user ID")
    amount: int = Field(..., ge=1, le=100000, description="XP amount to drain (1-100000)")
    reason: str = Field(default="API drain", description="Reason for the drain (for logging)")


class XPDrainResponse(BaseModel):
    """Response for XP drain operation."""

    success: bool = True
    user_id: int
    xp_drained: int
    old_xp: int
    new_xp: int
    old_level: int
    new_level: int
    level_dropped: bool


@router.post("/drain", response_model=XPDrainResponse)
async def drain_xp(
    request: Request,
    body: XPDrainRequest,
    api_key: str = Depends(require_api_key),
) -> JSONResponse:
    """
    Drain XP from a user (subtractive).

    Requires X-API-Key header for authentication.
    XP cannot go below 0.

    Request Body:
    - user_id: Discord user ID
    - amount: XP to drain (1-100000)
    - reason: Optional reason for logging
    """
    client_ip = get_client_ip(request)
    cache = get_cache_service()

    try:
        guild_id = config.GUILD_ID
        user_data = await asyncio.to_thread(db.get_user_xp, body.user_id, guild_id)

        if not user_data:
            return JSONResponse(
                content={"error": "User not found", "success": False},
                status_code=404,
            )

        old_xp = user_data.get("xp", 0)
        old_level = user_data.get("level", 0)

        # Calculate new XP (cannot go below 0)
        new_xp = max(0, old_xp - body.amount)
        actual_drain = old_xp - new_xp
        new_level = level_from_xp(new_xp)

        # Set XP in database
        await asyncio.to_thread(db.set_xp, body.user_id, guild_id, new_xp, new_level)

        logger.tree("XP Drained via API", [
            ("ID", str(body.user_id)),
            ("Drained", f"-{actual_drain}"),
            ("XP", f"{old_xp} -> {new_xp}"),
            ("Level", f"{old_level} -> {new_level}" if new_level != old_level else str(new_level)),
            ("Reason", body.reason[:50]),
            ("Client IP", client_ip),
        ], emoji="⬇️")

        # Clear response cache
        await cache.clear_responses()

        # Broadcast XP change to dashboard via WebSocket
        if actual_drain > 0:
            ws = get_ws_manager()
            ws._stats["xp"] = max(0, ws._stats["xp"] - actual_drain)
            await ws.broadcast_stat("xp", ws._stats["xp"])

        return JSONResponse(
            content=XPDrainResponse(
                success=True,
                user_id=body.user_id,
                xp_drained=actual_drain,
                old_xp=old_xp,
                new_xp=new_xp,
                old_level=old_level,
                new_level=new_level,
                level_dropped=new_level < old_level,
            ).model_dump()
        )

    except Exception as e:
        logger.error_tree("XP Drain API Error", e, [
            ("ID", str(body.user_id)),
            ("Amount", str(body.amount)),
            ("Client IP", client_ip),
        ])
        return JSONResponse(
            content={"error": "Internal server error"},
            status_code=500,
        )
