"""
SyriaBot - WebSocket Router
===========================

Real-time message count updates via WebSocket.

Author: حَـــــنَّـــــا
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.services.websocket import get_ws_manager


router = APIRouter(prefix="/api/syria", tags=["WebSocket"])


@router.websocket("/ws/messages")
async def messages_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time message count updates.

    Sends current count on connect, then broadcasts on every new message.
    """
    ws_manager = get_ws_manager()

    await ws_manager.connect(websocket)

    try:
        # Send current count immediately
        await websocket.send_json({
            "type": "message_count",
            "data": {"total_messages": ws_manager.message_count}
        })

        # Keep connection alive
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket)


__all__ = ["router"]
