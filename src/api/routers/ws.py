"""
SyriaBot - WebSocket Router
===========================

Real-time stats updates via WebSocket.

Author: حَـــــنَّـــــا
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.services.websocket import get_ws_manager


router = APIRouter(prefix="/api/syria", tags=["WebSocket"])


@router.websocket("/ws/stats")
async def stats_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time server stats.

    Sends all stats on connect, then broadcasts updates as they happen:
    - members: on join/leave
    - online: every 30 seconds
    - boosts: on boost/unboost
    - messages: on every message
    """
    ws_manager = get_ws_manager()

    await ws_manager.connect(websocket)

    try:
        # Keep connection alive
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket)


# Legacy endpoint for backwards compatibility
@router.websocket("/ws/messages")
async def messages_websocket(websocket: WebSocket):
    """Legacy endpoint - redirects to stats websocket."""
    ws_manager = get_ws_manager()

    await ws_manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket)


__all__ = ["router"]
