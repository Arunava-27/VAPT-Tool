"""
Network discovery and node VAPT endpoints
"""

import uuid
import subprocess
import re
import socket
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ....db.session import get_db
from ....models.user import User
from ....models.network import NetworkNode, NetworkScan
from .auth import get_current_active_user

router = APIRouter()

# Module-level singleton for Celery — same pattern as scans.py
_celery_app = None


def _get_celery_app():
    global _celery_app
    if _celery_app is None:
        from celery import Celery
        import os
        broker = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672/")
        backend = os.getenv("CELERY_RESULT_BACKEND", "redis://:redis123@redis:6379/0")
        _celery_app = Celery(broker=broker, backend=backend)
    return _celery_app


def _get_network_interfaces() -> List[Dict]:
    """Get all non-loopback network interfaces with IP/subnet info."""
    interfaces = []
    try:
        result = subprocess.run(
            ["ip", "-o", "addr", "show"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            iface = parts[1]
            if iface == "lo":
                continue
            family = parts[2]
            if family not in ("inet", "inet6"):
                continue
            cidr = parts[3]
            ip, prefix = cidr.split("/") if "/" in cidr else (cidr, "24")
            if family == "inet":
                octets = ip.split(".")
                network = f"{octets[0]}.{octets[1]}.{octets[2]}.0/{prefix}"
                interfaces.append({
                    "interface": iface,
                    "ip": ip,
                    "prefix": int(prefix),
                    "network_range": network,
                    "family": "ipv4",
                })
    except Exception:
        pass
    return interfaces


@router.get("/status")
async def network_status(
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Return current network interfaces and detected subnets."""
    interfaces = _get_network_interfaces()
    hostname = socket.gethostname()
    try:
        host_ip = socket.gethostbyname(hostname)
    except Exception:
        host_ip = "unknown"
    return {
        "hostname": hostname,
        "host_ip": host_ip,
        "interfaces": interfaces,
        "primary_range": interfaces[0]["network_range"] if interfaces else None,
    }


class DiscoverRequest(BaseModel):
    network_range: Optional[str] = None


@router.post("/discover")
async def discover_network(
    body: DiscoverRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Trigger a network discovery scan (dispatches to nmap worker)."""
    scan = NetworkScan(
        scan_type="discovery",
        network_range=body.network_range,
        status="pending",
        created_by=current_user.id,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    celery_app = _get_celery_app()
    task = celery_app.send_task(
        "nmap.network_discover",
        kwargs={"task_data": {
            "network_range": body.network_range,
            "scan_id": str(scan.id),
        }},
        queue="nmap",
    )
    # Store celery task ID so cancel can revoke it
    scan.result = {"celery_task_id": task.id}
    db.commit()

    return {"scan_id": str(scan.id), "status": "pending", "message": "Discovery scan started"}


@router.get("/nodes")
async def list_nodes(
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all discovered network nodes."""
    nodes = db.query(NetworkNode).order_by(NetworkNode.last_seen_at.desc()).all()
    return [_node_to_dict(n) for n in nodes]


@router.get("/nodes/{node_id}")
async def get_node(
    node_id: str,
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    node = db.query(NetworkNode).filter(NetworkNode.id == uuid.UUID(node_id)).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return _node_to_dict(node)


class NodeScanRequest(BaseModel):
    profile: str = "comprehensive"  # quick, comprehensive, vuln


@router.post("/nodes/{node_id}/scan")
async def scan_node(
    node_id: str,
    body: NodeScanRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Launch a port/vuln scan against a specific node."""
    node = db.query(NetworkNode).filter(NetworkNode.id == uuid.UUID(node_id)).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    scan = NetworkScan(
        scan_type=f"node_{body.profile}",
        target=node.ip_address,
        status="pending",
        created_by=current_user.id,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    celery_app = _get_celery_app()
    task = celery_app.send_task(
        "nmap.node_scan",
        kwargs={"task_data": {
            "target": node.ip_address,
            "scan_id": str(scan.id),
            "node_id": str(node.id),
            "profile": body.profile,
        }},
        queue="nmap",
    )
    scan.result = {"celery_task_id": task.id}
    db.commit()

    return {
        "scan_id": str(scan.id),
        "status": "pending",
        "message": f"Node scan ({body.profile}) started on {node.ip_address}",
    }


@router.get("/scans/{scan_id}")
async def get_scan(
    scan_id: str,
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    scan = db.query(NetworkScan).filter(NetworkScan.id == uuid.UUID(scan_id)).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return _scan_to_dict(scan)


@router.get("/scans")
async def list_scans(
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    scans = db.query(NetworkScan).order_by(NetworkScan.started_at.desc()).limit(50).all()
    return [_scan_to_dict(s) for s in scans]


@router.delete("/nodes/{node_id}")
async def delete_node(
    node_id: str,
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    node = db.query(NetworkNode).filter(NetworkNode.id == uuid.UUID(node_id)).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    db.delete(node)
    db.commit()
    return {"ok": True, "message": f"Node {node_id} deleted"}


@router.get("/host-interfaces")
async def host_interfaces(
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Get network interfaces from the nmap worker (runs with host networking).
    These reflect the Docker host's REAL LAN interfaces, unlike /status which
    shows Docker bridge IPs inside the api-gateway container.
    """
    try:
        celery = _get_celery_app()
        task = celery.send_task("nmap.get_interfaces", queue="nmap")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: task.get(timeout=10))
        ifaces = result.get("interfaces", []) if isinstance(result, dict) else []
        gateway_ip = result.get("gateway_ip") if isinstance(result, dict) else None
        err = result.get("error") if isinstance(result, dict) else None
        lan_ifaces = [i for i in ifaces if i.get("is_lan")]
        docker_only = len(ifaces) > 0 and len(lan_ifaces) == 0
        return {
            "interfaces": ifaces,
            "lan_interfaces": lan_ifaces,
            "docker_only": docker_only,
            "has_lan_access": len(lan_ifaces) > 0,
            "primary_range": lan_ifaces[0]["network_range"] if lan_ifaces else None,
            "gateway_ip": gateway_ip,
            "error": err,
        }
    except Exception as exc:
        return {
            "interfaces": [],
            "lan_interfaces": [],
            "docker_only": None,
            "has_lan_access": False,
            "primary_range": None,
            "error": str(exc),
        }


@router.post("/scans/{scan_id}/cancel")
async def cancel_scan(
    scan_id: str,
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Cancel a pending or running scan."""
    scan = db.query(NetworkScan).filter(NetworkScan.id == uuid.UUID(scan_id)).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel scan in state: {scan.status}")

    # Revoke the Celery task if we stored its ID
    celery_task_id = (scan.result or {}).get("celery_task_id")
    if celery_task_id:
        try:
            celery = _get_celery_app()
            celery.control.revoke(celery_task_id, terminate=True, signal="SIGTERM")
        except Exception:
            pass  # Revoke is best-effort

    scan.status = "cancelled"
    scan.completed_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Scan cancelled"}


def _node_to_dict(n: NetworkNode) -> Dict[str, Any]:    return {
        "id": str(n.id),
        "ip_address": n.ip_address,
        "mac_address": n.mac_address,
        "hostname": n.hostname,
        "os_family": n.os_family,
        "os_version": n.os_version,
        "device_type": n.device_type,
        "open_ports": n.open_ports or [],
        "services": n.services or [],
        "status": n.status,
        "network_range": n.network_range,
        "first_discovered_at": n.first_discovered_at.isoformat() if n.first_discovered_at else None,
        "last_seen_at": n.last_seen_at.isoformat() if n.last_seen_at else None,
    }


def _scan_to_dict(s: NetworkScan) -> Dict[str, Any]:
    return {
        "id": str(s.id),
        "scan_type": s.scan_type,
        "target": s.target,
        "network_range": s.network_range,
        "status": s.status,
        "nodes_found": s.nodes_found,
        "result": s.result or {},
        "error": s.error,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
    }


# ─── Import endpoint (for host-side scanner agent) ───────────────────────────

class ImportNodeData(BaseModel):
    ip: str
    mac: Optional[str] = None
    hostname: Optional[str] = None
    device_type: Optional[str] = "unknown"

class ImportRequest(BaseModel):
    network_range: str
    nodes: List[ImportNodeData]

@router.post("/import")
async def import_scan_results(
    body: ImportRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Accept scan results from an external host-side scanner agent.
    Creates a completed NetworkScan record and upserts all discovered nodes.
    Used when the platform runs on Windows Docker Desktop (where containers
    can't reach the real LAN) — the agent runs natively on the host instead.
    """
    scan = NetworkScan(
        scan_type="discovery",
        network_range=body.network_range,
        status="completed",
        nodes_found=len(body.nodes),
        created_by=current_user.id,
        completed_at=datetime.utcnow(),
    )
    db.add(scan)
    db.flush()

    saved_nodes = []
    for n in body.nodes:
        node = db.query(NetworkNode).filter(NetworkNode.ip_address == n.ip).first()
        if node:
            node.mac_address = n.mac or node.mac_address
            node.hostname = n.hostname or node.hostname
            node.device_type = n.device_type or node.device_type
            node.status = "active"
            node.last_seen_at = datetime.utcnow()
        else:
            node = NetworkNode(
                ip_address=n.ip,
                mac_address=n.mac,
                hostname=n.hostname,
                device_type=n.device_type or "unknown",
                network_range=body.network_range,
                status="active",
                last_seen_at=datetime.utcnow(),
            )
            db.add(node)
            db.flush()
        saved_nodes.append({"id": str(node.id), "ip": n.ip})

    db.commit()
    return {
        "scan_id": str(scan.id),
        "status": "completed",
        "nodes_imported": len(saved_nodes),
        "network_range": body.network_range,
        "nodes": saved_nodes,
    }
