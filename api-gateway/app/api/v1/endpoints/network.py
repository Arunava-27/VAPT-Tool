"""
Network discovery and node VAPT endpoints
"""

import uuid
import subprocess
import re
import socket
import asyncio
import httpx
from datetime import datetime
from typing import List, Optional, Dict, Any

import sys as _sys
HOST_AGENT_URL = (
    "http://localhost:9999" if _sys.platform == "win32"
    else "http://host.docker.internal:9999"
)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ....db.session import get_db
from ....models.user import User
from ....models.network import NetworkNode, NetworkScan, HostVulnerability
from ....models.scan import Scan
from ....models.audit_log import AuditLog
from .auth import get_current_active_user


def _write_audit_log(
    db: Session,
    user: User,
    action: str,
    resource_type: str = None,
    resource_id: str = None,
    details: dict = None,
) -> None:
    """Write a single entry to the audit_logs table (best-effort, never raises)."""
    try:
        entry = AuditLog(
            tenant_id=str(user.tenant_id),
            user_id=str(user.id),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
        db.add(entry)
        db.flush()
    except Exception:
        pass

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


@router.get("/host-agent-status")
async def host_agent_status(
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Check whether the host discovery agent is reachable."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{HOST_AGENT_URL}/health")
            if resp.status_code == 200:
                data = resp.json()
                return {"available": True, "platform": data.get("platform", "unknown"),
                        "hostname": data.get("hostname")}
    except Exception:
        pass
    return {"available": False, "platform": None, "hostname": None}


@router.post("/discover")
async def discover_network(
    body: DiscoverRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Trigger a network discovery scan.

    Strategy:
    1. Try the host agent (host.docker.internal:9999) — gives real LAN access.
    2. Fall back to nmap Celery worker (Docker-only, limited to container networks).
    """
    # ── 1. Try host agent ──────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{HOST_AGENT_URL}/discover",
                json={"network_range": body.network_range},
            )
            if resp.status_code == 200:
                data = resp.json()
                network_range = data.get("network_range", body.network_range or "unknown")
                nodes_raw = data.get("nodes", [])

                scan = NetworkScan(
                    scan_type="discovery",
                    network_range=network_range,
                    status="completed",
                    nodes_found=len(nodes_raw),
                    created_by=current_user.id,
                    completed_at=datetime.utcnow(),
                )
                db.add(scan)
                db.flush()

                # Mark nodes NOT found in this scan as inactive.
                # Use the scanned IPs as the authoritative "alive" set.
                found_ips = {n.get("ip") for n in nodes_raw if n.get("ip")}
                if found_ips:
                    db.query(NetworkNode).filter(
                        NetworkNode.network_range == network_range,
                        ~NetworkNode.ip_address.in_(found_ips)
                    ).update({"status": "inactive"}, synchronize_session=False)

                for n in nodes_raw:
                    ip = n.get("ip")
                    if not ip:
                        continue
                    node = db.query(NetworkNode).filter(NetworkNode.ip_address == ip).first()
                    if node:
                        node.mac_address   = n.get("mac") or node.mac_address
                        node.hostname      = n.get("hostname") or node.hostname
                        node.device_type   = n.get("device_type") or node.device_type
                        node.status        = "active"
                        node.last_seen_at  = datetime.utcnow()
                    else:
                        node = NetworkNode(
                            ip_address   = ip,
                            mac_address  = n.get("mac"),
                            hostname     = n.get("hostname"),
                            device_type  = n.get("device_type", "unknown"),
                            network_range= network_range,
                            status       = "active",
                            last_seen_at = datetime.utcnow(),
                        )
                        db.add(node)
                db.commit()

                _write_audit_log(db, current_user, "network_discovery_completed",
                    resource_type="network_scan", resource_id=str(scan.id),
                    details={"range": network_range, "nodes_found": len(nodes_raw), "source": "host-agent"})
                db.commit()
                return {
                    "scan_id": str(scan.id),
                    "status": "completed",
                    "source": "host-agent",
                    "method": data.get("method", "arp"),
                    "message": f"Discovered {len(nodes_raw)} nodes via host agent",
                    "nodes_found": len(nodes_raw),
                }
    except Exception:
        pass  # host agent unavailable — fall through to Celery worker

    # ── 2. Fall back: Celery nmap worker (Docker-only) ─────────────────────
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
    scan.result = {"celery_task_id": task.id}
    _write_audit_log(db, current_user, "network_discovery_started",
        resource_type="network_scan", resource_id=str(scan.id),
        details={"range": body.network_range, "source": "celery"})
    db.commit()

    return {
        "scan_id": str(scan.id),
        "status": "pending",
        "source": "docker-worker",
        "message": "Discovery scan started (Docker worker — start host agent for real LAN access)",
    }


@router.get("/nodes")
async def list_nodes(
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all discovered network nodes (active only)."""
    nodes = db.query(NetworkNode).filter(NetworkNode.status == "active").order_by(NetworkNode.last_seen_at.desc()).all()
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
    """Launch a port/vuln scan. Tries host agent first (real LAN access), falls back to Celery."""
    node = db.query(NetworkNode).filter(NetworkNode.id == uuid.UUID(node_id)).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # ── 1. Try host agent ────────────────────────────────────────────────────
    try:
        timeout = {"ping": 30, "quick": 100, "comprehensive": 240, "vuln": 380}.get(body.profile, 100)
        async with httpx.AsyncClient(timeout=float(timeout)) as client:
            resp = await client.post(
                f"{HOST_AGENT_URL}/scan-node",
                json={"target": node.ip_address, "profile": body.profile},
            )
            if resp.status_code == 200:
                data = resp.json()
                scan_status = data.get("status", "completed")
                open_ports = data.get("open_ports", [])
                services = data.get("services", [])
                os_family = data.get("os_family")
                os_version = data.get("os_version")
                vulns_raw = data.get("vulnerabilities", [])

                scan = NetworkScan(
                    scan_type=f"node_{body.profile}",
                    target=node.ip_address,
                    status="completed" if scan_status.startswith("completed") else scan_status[:20],
                    created_by=current_user.id,
                    completed_at=datetime.utcnow(),
                    result={"open_ports": open_ports, "services": services,
                            "os_family": os_family, "os_version": os_version},
                )
                db.add(scan)
                db.flush()

                # Also create a main Scan record so this appears in the Scans list
                main_scan = Scan(
                    name=f"Node scan — {node.ip_address} ({body.profile})",
                    description=f"Port/vulnerability scan on {node.ip_address} via host agent",
                    scan_type="network",
                    target=node.ip_address,
                    status="running",
                    tenant_id=str(current_user.tenant_id),
                    created_by_id=str(current_user.id),
                    started_at=datetime.utcnow(),
                )
                db.add(main_scan)
                db.flush()

                # Update node with scan results
                node.open_ports = open_ports
                node.services = services
                node.os_family = os_family
                node.os_version = os_version
                node.last_scan_id = scan.id
                node.last_seen_at = datetime.utcnow()

                # Save vulnerabilities
                db.query(HostVulnerability).filter(
                    HostVulnerability.node_id == node.id
                ).delete()
                for v in vulns_raw:
                    hv = HostVulnerability(
                        node_id=node.id,
                        scan_id=scan.id,
                        vuln_id=v.get("vuln_id", ""),
                        title=v.get("title", ""),
                        severity=v.get("severity", "info"),
                        description=v.get("description"),
                        cve_id=v.get("cve_id"),
                        cvss_score=v.get("cvss_score"),
                        port=v.get("port"),
                        protocol=v.get("protocol"),
                        service=v.get("service"),
                        evidence=v.get("evidence"),
                    )
                    db.add(hv)

                # Compute risk score
                sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
                for v in vulns_raw:
                    s = v.get("severity", "info")
                    if s in sev_counts:
                        sev_counts[s] += 1
                node.risk_score = min(100,
                    sev_counts["critical"] * 40 + sev_counts["high"] * 15 +
                    sev_counts["medium"] * 5 + sev_counts["low"] * 1
                )

                db.commit()

                # Update main_scan to completed with results
                main_scan.status = "completed"
                main_scan.completed_at = datetime.utcnow()
                main_scan.result_summary = {
                    "open_ports": len(open_ports),
                    "vulnerabilities": len(vulns_raw),
                    **sev_counts,
                }
                _write_audit_log(db, current_user, "node_scan_completed",
                    resource_type="network_node", resource_id=node_id,
                    details={"ip": node.ip_address, "profile": body.profile,
                             "ports": len(open_ports), "vulns": len(vulns_raw), "source": "host-agent"})
                db.commit()
                return {
                    "scan_id": str(scan.id),
                    "status": "completed",
                    "source": "host-agent",
                    "open_ports": len(open_ports),
                    "vulnerabilities": len(vulns_raw),
                    "message": f"Scan complete — {len(open_ports)} ports, {len(vulns_raw)} findings",
                }
    except Exception:
        pass  # fall back to Celery worker

    # ── 2. Fall back: Celery worker ──────────────────────────────────────────
    scan = NetworkScan(
        scan_type=f"node_{body.profile}",
        target=node.ip_address,
        status="pending",
        created_by=current_user.id,
    )
    db.add(scan)
    db.flush()

    # Create main Scan record so this appears in the Scans list
    main_scan = Scan(
        name=f"Node scan — {node.ip_address} ({body.profile})",
        description=f"Port/vulnerability scan on {node.ip_address} via Celery worker",
        scan_type="network",
        target=node.ip_address,
        status="queued",
        tenant_id=str(current_user.tenant_id),
        created_by_id=str(current_user.id),
        started_at=datetime.utcnow(),
    )
    db.add(main_scan)
    db.flush()

    _write_audit_log(db, current_user, "node_scan_started",
        resource_type="network_node", resource_id=node_id,
        details={"ip": node.ip_address, "profile": body.profile, "source": "celery"})
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
        "source": "celery",
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


@router.get("/capture-interfaces")
async def capture_interfaces(
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Return interfaces available for packet capture via scapy/Npcap."""
    from .ws import _get_capture_interfaces
    try:
        return {"interfaces": _get_capture_interfaces()}
    except Exception as exc:
        return {"interfaces": [], "error": str(exc)}


@router.get("/host-interfaces")
async def host_interfaces(
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Get network interfaces from the host agent (runs natively on the Windows host).
    Falls back to a local Python-based detection if the host agent is unavailable.
    """
    import ipaddress

    def _local_interfaces():
        """Fallback: detect interfaces via ipconfig (Windows only)."""
        ifaces = []
        try:
            r = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=5)
            adapter = None
            ip = None
            for line in r.stdout.splitlines():
                stripped = line.strip()
                if "adapter" in stripped.lower() and stripped.endswith(":"):
                    adapter = stripped.rstrip(":")
                    ip = None
                elif "IPv4" in stripped or "IP Address" in stripped:
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", stripped)
                    if m:
                        ip = m.group(1)
                        try:
                            net = ipaddress.ip_network(f"{ip}/24", strict=False)
                            ifaces.append({
                                "interface": adapter or "unknown",
                                "ip": ip,
                                "prefix": 24,
                                "network_range": str(net),
                                "family": "inet",
                                "is_docker": "docker" in (adapter or "").lower() or ip.startswith("172."),
                                "is_lan": not ip.startswith("127.") and not ip.startswith("172."),
                            })
                        except Exception:
                            pass
        except Exception:
            pass
        return ifaces

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{HOST_AGENT_URL}/interfaces")
            resp.raise_for_status()
            data = resp.json()

        raw = data.get("interfaces", [])
        ifaces = []
        for r in raw:
            ip = r.get("ip", "")
            try:
                net = ipaddress.ip_network(f"{ip}/24", strict=False)
                network_range = str(net)
            except Exception:
                network_range = f"{ip}/24"
            name = r.get("interface", "")
            is_docker = (
                "docker" in name.lower()
                or "vethernet" in name.lower()
                or ip.startswith("172.")
                or ip.startswith("10.0.")
            )
            is_lan = r.get("is_private", False) and not is_docker and not ip.startswith("127.")
            ifaces.append({
                "interface": name,
                "ip": ip,
                "prefix": 24,
                "network_range": network_range,
                "family": "inet",
                "is_docker": is_docker,
                "is_lan": is_lan,
            })

        lan_ifaces = [i for i in ifaces if i.get("is_lan")]
        docker_only = len(ifaces) > 0 and len(lan_ifaces) == 0
        return {
            "interfaces": ifaces,
            "lan_interfaces": lan_ifaces,
            "docker_only": docker_only,
            "has_lan_access": len(lan_ifaces) > 0,
            "primary_range": lan_ifaces[0]["network_range"] if lan_ifaces else None,
            "gateway_ip": None,
            "error": None,
        }
    except Exception:
        # Fallback to local subprocess detection
        ifaces = _local_interfaces()
        lan_ifaces = [i for i in ifaces if i.get("is_lan")]
        return {
            "interfaces": ifaces,
            "lan_interfaces": lan_ifaces,
            "docker_only": len(ifaces) > 0 and len(lan_ifaces) == 0,
            "has_lan_access": len(lan_ifaces) > 0,
            "primary_range": lan_ifaces[0]["network_range"] if lan_ifaces else None,
            "gateway_ip": None,
            "error": None,
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
        "risk_score": n.risk_score or 0,
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


def _vuln_to_dict(v: HostVulnerability) -> Dict[str, Any]:
    return {
        "id": str(v.id),
        "node_id": str(v.node_id),
        "scan_id": str(v.scan_id) if v.scan_id else None,
        "vuln_id": v.vuln_id,
        "title": v.title,
        "severity": v.severity,
        "description": v.description,
        "cve_id": v.cve_id,
        "cvss_score": v.cvss_score,
        "port": v.port,
        "protocol": v.protocol,
        "service": v.service,
        "evidence": v.evidence,
        "remediation": v.remediation,
        "status": v.status,
        "discovered_at": v.discovered_at.isoformat() if v.discovered_at else None,
    }


class VulnStatusRequest(BaseModel):
    status: str  # open, accepted, fixed, false_positive


@router.get("/nodes/{node_id}/vulnerabilities")
async def get_node_vulnerabilities(
    node_id: str,
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all vulnerabilities for a node. Falls back to port findings if none scanned."""
    node = db.query(NetworkNode).filter(NetworkNode.id == uuid.UUID(node_id)).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    vulns = db.query(HostVulnerability).filter(
        HostVulnerability.node_id == uuid.UUID(node_id)
    ).order_by(HostVulnerability.discovered_at.desc()).all()

    if vulns:
        return [_vuln_to_dict(v) for v in vulns]

    # Derive info findings from services if no vuln scan yet
    result = []
    for svc in (node.services or []):
        result.append({
            "id": str(uuid.uuid4()),
            "node_id": node_id,
            "scan_id": None,
            "vuln_id": f"service-{svc.get('port')}-{svc.get('protocol')}",
            "title": f"Open Port: {svc.get('service', 'unknown')} on {svc.get('port')}/{svc.get('protocol')}",
            "severity": "info",
            "description": f"Port {svc.get('port')}/{svc.get('protocol')} is open running {svc.get('product', '')} {svc.get('version', '')}".strip(),
            "cve_id": None,
            "cvss_score": None,
            "port": svc.get("port"),
            "protocol": svc.get("protocol"),
            "service": svc.get("service"),
            "evidence": None,
            "remediation": None,
            "status": "open",
            "discovered_at": node.last_seen_at.isoformat() if node.last_seen_at else datetime.utcnow().isoformat(),
        })
    return result


def _derive_service_vulns(node: NetworkNode) -> List[Dict[str, Any]]:
    """Derive info-level findings from a node's services JSONB (used when no vuln scan done)."""
    result = []
    services = node.services if isinstance(node.services, list) else []
    for svc in services:
        port = svc.get("port")
        proto = svc.get("protocol", "tcp")
        svc_name = svc.get("service", "unknown")
        product = svc.get("product", "")
        version = svc.get("version", "")
        desc = f"Port {port}/{proto} is open running {product} {version}".strip()
        result.append({
            "id": f"derived-{node.id}-{port}-{proto}",
            "node_id": str(node.id),
            "node_ip": node.ip_address,
            "scan_id": None,
            "vuln_id": f"service-{port}-{proto}",
            "title": f"Open Port: {svc_name} on {port}/{proto}",
            "severity": "info",
            "description": desc,
            "cve_id": None,
            "cvss_score": None,
            "port": port,
            "protocol": proto,
            "service": svc_name,
            "evidence": None,
            "remediation": None,
            "status": "open",
            "discovered_at": node.last_seen_at.isoformat() if node.last_seen_at else datetime.utcnow().isoformat(),
        })
    return result


@router.get("/vulnerabilities")
async def get_all_vulnerabilities(
    severity: Optional[str] = None,
    status: Optional[str] = None,
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """All vulnerabilities across all nodes. Returns DB vulns + derived service findings."""
    # DB vulns (from actual scans)
    query = db.query(HostVulnerability)
    if severity:
        query = query.filter(HostVulnerability.severity == severity)
    if status:
        query = query.filter(HostVulnerability.status == status)
    db_vulns = query.order_by(HostVulnerability.discovered_at.desc()).all()

    # Build set of nodes that already have real vuln records
    scanned_node_ids = {str(v.node_id) for v in db_vulns}

    # Enrich DB vulns with node IP
    result = []
    node_ip_cache: Dict[str, str] = {}
    for v in db_vulns:
        d = _vuln_to_dict(v)
        nid = str(v.node_id)
        if nid not in node_ip_cache:
            n = db.query(NetworkNode).filter(NetworkNode.id == v.node_id).first()
            node_ip_cache[nid] = n.ip_address if n else "unknown"
        d["node_ip"] = node_ip_cache[nid]
        result.append(d)

    # For nodes not yet scanned, derive from services (only when no severity filter or info matches)
    if not severity or severity == "info":
        nodes_with_services = db.query(NetworkNode).filter(
            NetworkNode.services.isnot(None)
        ).all()
        for node in nodes_with_services:
            if str(node.id) in scanned_node_ids:
                continue
            services = node.services if isinstance(node.services, list) else []
            if not services:
                continue
            derived = _derive_service_vulns(node)
            if status and status != "open":
                continue
            result.extend(derived)

    return result


@router.get("/summary")
async def get_network_summary(
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Summary: node counts, vuln counts, risk distribution."""
    total_nodes = db.query(NetworkNode).count()
    active_nodes = db.query(NetworkNode).filter(NetworkNode.status == "active").count()

    all_vulns = db.query(HostVulnerability).all()
    counts: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for v in all_vulns:
        counts[v.severity] = counts.get(v.severity, 0) + 1

    # Count derived info findings from services for unscanned nodes
    scanned_node_ids = {str(v.node_id) for v in all_vulns}
    nodes_with_services = db.query(NetworkNode).filter(NetworkNode.services.isnot(None)).all()
    for node in nodes_with_services:
        if str(node.id) in scanned_node_ids:
            continue
        services = node.services if isinstance(node.services, list) else []
        counts["info"] += len(services)

    # Per-node risk distribution (top 10 by risk score or port count)
    vuln_by_node: Dict[str, Dict[str, int]] = {}
    for v in all_vulns:
        nid = str(v.node_id)
        if nid not in vuln_by_node:
            vuln_by_node[nid] = {"critical": 0, "high": 0, "medium": 0}
        if v.severity in vuln_by_node[nid]:
            vuln_by_node[nid][v.severity] += 1

    nodes = db.query(NetworkNode).all()
    risk_distribution = []
    for n in nodes:
        nc = vuln_by_node.get(str(n.id), {})
        port_count = len(n.open_ports) if isinstance(n.open_ports, list) else 0
        if nc.get("critical", 0) > 0 or nc.get("high", 0) > 0 or nc.get("medium", 0) > 0 or port_count > 0:
            risk_distribution.append({
                "ip": n.ip_address,
                "risk_score": n.risk_score or 0,
                "critical": nc.get("critical", 0),
                "high": nc.get("high", 0),
                "medium": nc.get("medium", 0),
                "open_ports": port_count,
            })
    risk_distribution.sort(key=lambda x: (x["risk_score"], x["open_ports"]), reverse=True)

    return {
        "total_nodes": total_nodes,
        "active_nodes": active_nodes,
        "total_vulns": sum(counts.values()),
        "critical": counts["critical"],
        "high": counts["high"],
        "medium": counts["medium"],
        "low": counts["low"],
        "info": counts["info"],
        "risk_distribution": risk_distribution[:10],
    }


@router.post("/nodes/{node_id}/vulnerabilities/{vuln_id}/status")
async def update_vuln_status(
    node_id: str,
    vuln_id: str,
    body: VulnStatusRequest,
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Update a vulnerability's status."""
    valid_statuses = {"open", "accepted", "fixed", "false_positive"}
    if body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    vuln = db.query(HostVulnerability).filter(HostVulnerability.id == uuid.UUID(vuln_id)).first()
    if not vuln:
        raise HTTPException(status_code=404, detail="Vulnerability not found")
    vuln.status = body.status
    db.commit()
    return {"ok": True, "status": body.status}


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

    # Mark nodes NOT in this scan result as inactive
    found_ips = {n.ip for n in body.nodes}
    if found_ips:
        db.query(NetworkNode).filter(
            NetworkNode.network_range == body.network_range,
            ~NetworkNode.ip_address.in_(found_ips)
        ).update({"status": "inactive"}, synchronize_session=False)

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


# ─── Traffic Monitor ──────────────────────────────────────────────────────────

@router.get("/traffic")
async def get_traffic(
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Return active network connections on the host using psutil.
    Filters out loopback connections; enriches with process name where available.
    """
    try:
        import psutil
        connections = []
        for c in psutil.net_connections(kind="inet"):
            laddr = c.laddr
            raddr = c.raddr
            if not raddr:
                continue
            local_ip = laddr.ip if laddr else ""
            remote_ip = raddr.ip if raddr else ""
            # Skip pure-loopback
            if local_ip in ("127.0.0.1", "::1") and remote_ip in ("127.0.0.1", "::1"):
                continue
            proc_name = None
            try:
                if c.pid:
                    p = psutil.Process(c.pid)
                    proc_name = p.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            connections.append({
                "local_ip": local_ip,
                "local_port": laddr.port if laddr else None,
                "remote_ip": remote_ip,
                "remote_port": raddr.port if raddr else None,
                "status": c.status or "NONE",
                "pid": c.pid,
                "process_name": proc_name,
                "family": "IPv6" if ":" in local_ip else "IPv4",
            })
        # Sort: ESTABLISHED first, then by remote_ip
        connections.sort(key=lambda x: (x["status"] != "ESTABLISHED", x["remote_ip"]))
        return {"connections": connections, "total": len(connections), "error": None}
    except Exception as exc:
        return {"connections": [], "total": 0, "error": str(exc)}


# ─── Topology ─────────────────────────────────────────────────────────────────

@router.get("/topology")
async def get_topology(
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Return a topology graph (nodes + edges) derived from discovered NetworkNodes.
    All nodes are connected to the detected gateway. The host machine is also
    included as a special node.
    """
    import ipaddress
    import socket as _socket

    db_nodes = db.query(NetworkNode).filter(NetworkNode.status == "active").all()

    # Detect gateway and host IP from host-agent
    gateway_ip: Optional[str] = None
    host_ip: Optional[str] = None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{HOST_AGENT_URL}/interfaces")
            if resp.status_code == 200:
                data = resp.json()
                ifaces = data.get("interfaces", [])
                # Pick first private (non-WSL) IP as host IP
                for iface in ifaces:
                    ip = iface.get("ip", "")
                    name = iface.get("interface", "")
                    if (
                        ip and iface.get("is_private")
                        and not ip.startswith("172.")
                        and "wsl" not in name.lower()
                        and "docker" not in name.lower()
                    ):
                        host_ip = ip
                        break
    except Exception:
        pass

    try:
        host_ip = host_ip or _socket.gethostbyname(_socket.gethostname())
    except Exception:
        pass

    # Guess gateway: first .1 on the host subnet
    if host_ip and not gateway_ip:
        try:
            net = ipaddress.ip_network(f"{host_ip}/24", strict=False)
            gateway_ip = str(list(net.hosts())[0])  # x.x.x.1
        except Exception:
            pass

    topo_nodes = []
    topo_edges = []
    used_ids: set = set()

    def _safe_id(ip: str) -> str:
        return f"node-{ip.replace('.', '-').replace(':', '-')}"

    # Gateway node
    gw_id = _safe_id(gateway_ip) if gateway_ip else "node-gateway"
    topo_nodes.append({
        "id": gw_id,
        "type": "gateway",
        "ip": gateway_ip or "gateway",
        "hostname": "Gateway / Router",
        "device_type": "router",
        "risk_score": 0,
        "open_ports": [],
        "services": [],
        "status": "active",
        "is_gateway": True,
        "is_host": False,
    })
    used_ids.add(gw_id)

    # Host machine node
    if host_ip:
        host_id = _safe_id(host_ip)
        if host_id not in used_ids:
            topo_nodes.append({
                "id": host_id,
                "type": "host",
                "ip": host_ip,
                "hostname": _socket.gethostname(),
                "device_type": "pc",
                "risk_score": 0,
                "open_ports": [],
                "services": [],
                "status": "active",
                "is_gateway": False,
                "is_host": True,
            })
            used_ids.add(host_id)
            topo_edges.append({
                "id": f"edge-{host_id}-{gw_id}",
                "source": host_id,
                "target": gw_id,
                "type": "default",
            })

    # Discovered nodes
    for n in db_nodes:
        node_id = _safe_id(n.ip_address)
        if node_id in used_ids:
            continue
        used_ids.add(node_id)
        topo_nodes.append({
            "id": node_id,
            "db_id": str(n.id),
            "type": "device",
            "ip": n.ip_address,
            "hostname": n.hostname,
            "device_type": n.device_type or "unknown",
            "risk_score": n.risk_score or 0,
            "open_ports": n.open_ports or [],
            "services": n.services or [],
            "status": n.status,
            "mac_address": n.mac_address,
            "os_family": n.os_family,
            "last_seen_at": n.last_seen_at.isoformat() if n.last_seen_at else None,
            "is_gateway": False,
            "is_host": False,
        })
        topo_edges.append({
            "id": f"edge-{node_id}-{gw_id}",
            "source": node_id,
            "target": gw_id,
            "type": "default",
        })

    return {
        "nodes": topo_nodes,
        "edges": topo_edges,
        "gateway_ip": gateway_ip,
        "host_ip": host_ip,
    }
