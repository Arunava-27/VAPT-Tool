"""
Docker container logs endpoints.
Accesses Docker Engine API via Unix socket (mounted at /var/run/docker.sock).
"""
import re
import struct
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .auth import get_current_active_user
from ....models.user import User
from ....models.audit_log import AuditLog
from ....db.session import get_db

router = APIRouter()

DOCKER_SOCKET = "/var/run/docker.sock"

# Container categories for UI grouping
CONTAINER_CATEGORIES = {
    "data": ["vapt-postgres", "vapt-redis", "vapt-rabbitmq", "vapt-elasticsearch", "vapt-minio", "vapt-vault"],
    "backend": ["vapt-api-gateway", "vapt-orchestrator", "vapt-ai-engine", "vapt-ollama"],
    "workers": ["vapt-worker-nmap", "vapt-worker-zap", "vapt-worker-nikto", "vapt-worker-metasploit", "vapt-worker-sqlmap"],
    "frontend": ["vapt-frontend"],
    "init": ["vapt-data-init", "vapt-vault-init"],
}


def _get_category(name: str) -> str:
    for cat, names in CONTAINER_CATEGORIES.items():
        if name in names:
            return cat
    if "worker" in name:
        return "workers"
    return "other"


async def _docker_get(path: str, **kwargs) -> httpx.Response:
    transport = httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        return await client.get(path, timeout=10.0, **kwargs)


def _parse_docker_log_stream(raw: bytes) -> List[Dict[str, str]]:
    """Parse Docker multiplexed log stream format (8-byte header + payload)."""
    lines = []
    pos = 0
    while pos + 8 <= len(raw):
        stream_type = raw[pos]  # 1=stdout, 2=stderr
        size = struct.unpack(">I", raw[pos + 4:pos + 8])[0]
        pos += 8
        if pos + size > len(raw):
            break
        payload = raw[pos:pos + size].decode("utf-8", errors="replace")
        pos += size
        for line in payload.splitlines():
            line = line.strip()
            if line:
                # Strip ANSI escape codes
                clean = re.sub(r'\x1b\[[0-9;]*[mGKHF]', '', line)
                lines.append({
                    "text": clean,
                    "stream": "stderr" if stream_type == 2 else "stdout",
                })
    # Fallback: if parsing yields nothing, split raw as plain text
    if not lines:
        for line in raw.decode("utf-8", errors="replace").splitlines():
            clean = re.sub(r'\x1b\[[0-9;]*[mGKHF]', '', line.strip())
            if clean:
                lines.append({"text": clean, "stream": "stdout"})
    return lines


@router.get("/containers")
async def list_containers(
    _: User = Depends(get_current_active_user),
) -> List[Dict[str, Any]]:
    """List all Docker containers with status and category."""
    try:
        resp = await _docker_get("/containers/json", params={"all": "true"})
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Docker socket unavailable: {exc}")

    containers = []
    for c in data:
        names = c.get("Names", [])
        name = names[0].lstrip("/") if names else c["Id"][:12]
        containers.append({
            "id": c["Id"][:12],
            "full_id": c["Id"],
            "name": name,
            "image": c.get("Image", ""),
            "status": c.get("Status", ""),
            "state": c.get("State", ""),
            "category": _get_category(name),
        })

    # Sort by category priority
    order = ["backend", "workers", "data", "frontend", "init", "other"]
    containers.sort(key=lambda x: (order.index(x["category"]) if x["category"] in order else 99, x["name"]))
    return containers


@router.get("/containers/{container_id}")
async def get_logs(
    container_id: str,
    tail: int = Query(default=300, ge=10, le=5000),
    stdout: bool = Query(default=True),
    stderr: bool = Query(default=True),
    since: Optional[int] = Query(default=None),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Get logs for a specific container."""
    params: Dict[str, Any] = {
        "stdout": "true" if stdout else "false",
        "stderr": "true" if stderr else "false",
        "tail": str(tail),
        "timestamps": "true",
    }
    if since:
        params["since"] = str(since)
    try:
        resp = await _docker_get(f"/containers/{container_id}/logs", params=params)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Container not found")
        resp.raise_for_status()
        lines = _parse_docker_log_stream(resp.content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to fetch logs: {exc}")

    return {
        "container_id": container_id,
        "lines": lines,
        "total": len(lines),
    }


@router.get("/audit")
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    action: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return paginated audit log entries for the current tenant."""
    q = db.query(AuditLog).filter(AuditLog.tenant_id == str(current_user.tenant_id))
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)

    total = q.count()
    entries = (
        q.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Resolve user emails for display
    user_ids = {e.user_id for e in entries if e.user_id}
    users_map: Dict[str, str] = {}
    if user_ids:
        from ....models.user import User as UserModel
        rows = db.query(UserModel.id, UserModel.email).filter(
            UserModel.id.in_(list(user_ids))
        ).all()
        users_map = {str(r.id): r.email for r in rows}

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "entries": [
            {
                "id": e.id,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "details": e.details or {},
                "user_email": users_map.get(str(e.user_id), "system"),
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ],
    }
