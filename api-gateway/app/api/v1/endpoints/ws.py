"""
WebSocket endpoints for real-time scan status updates.

Clients connect to /api/v1/ws/scans/{scan_id}?token=<jwt>
The server pushes a JSON status message every 2 seconds while the scan
is active, then sends a final message and closes the connection.
"""

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from ....db.session import SessionLocal
from ....core.security import decode_token
from ....models.scan import Scan

router = APIRouter()
logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2.0  # seconds between DB queries
_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def _get_scan_payload(db: Session, scan_id: str, tenant_id: str) -> dict | None:
    """Load scan from DB and return a serialisable dict, or None if not found."""
    scan: Scan | None = db.query(Scan).filter(
        Scan.id == scan_id,
        Scan.tenant_id == tenant_id,
    ).first()
    if not scan:
        return None
    rs = scan.result_summary or {}
    return {
        "type": "scan_update",
        "id": str(scan.id),
        "status": scan.status,
        "progress_percentage": rs.get("progress_percentage", 0),
        "result_summary": rs,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        "error": scan.error,
    }


@router.websocket("/scans/{scan_id}")
async def scan_status_ws(websocket: WebSocket, scan_id: str):
    """
    WebSocket endpoint for real-time scan status.

    Authentication: pass the JWT as a query parameter `token`.
    Messages are pushed every 2 seconds until the scan reaches a
    terminal state (completed / failed / cancelled).
    """
    token: str | None = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Validate JWT and extract tenant
    try:
        payload = decode_token(token)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    tenant_id: str | None = payload.get("tenant_id")
    if not tenant_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Validate scan_id format
    try:
        UUID(scan_id)
    except ValueError:
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
        return

    await websocket.accept()
    logger.info("WS connected: scan=%s tenant=%s", scan_id, tenant_id)

    try:
        while True:
            db = SessionLocal()
            try:
                data = await asyncio.to_thread(_get_scan_payload, db, scan_id, tenant_id)
            finally:
                db.close()

            if data is None:
                await websocket.send_text(json.dumps({"type": "error", "detail": "Scan not found"}))
                break

            await websocket.send_text(json.dumps(data))

            if data["status"] in _TERMINAL_STATUSES:
                # Final update sent — close gracefully
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                break

            await asyncio.sleep(_POLL_INTERVAL)

    except WebSocketDisconnect:
        logger.info("WS disconnected: scan=%s", scan_id)
    except Exception as exc:
        logger.error("WS error for scan %s: %s", scan_id, exc, exc_info=True)
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
