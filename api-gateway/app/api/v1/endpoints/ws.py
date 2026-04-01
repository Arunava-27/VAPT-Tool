"""
WebSocket endpoints:
  /ws/scans/{scan_id}  – real-time scan status
  /ws/traffic          – live packet capture (Wireshark-style, via scapy + Npcap)
  /ws/discovery        – real-time network node discovery stream
"""

import asyncio
import json
import logging
import threading
import time
import sys as _sys
from uuid import UUID
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from ....db.session import SessionLocal
from ....core.security import decode_token
from ....models.scan import Scan

HOST_AGENT_URL = (
    "http://localhost:9999" if _sys.platform == "win32"
    else "http://host.docker.internal:9999"
)

router = APIRouter()
logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2.0
_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _auth_ws(websocket: WebSocket) -> Optional[dict]:
    """Validate JWT from query param; return payload or None."""
    token = websocket.query_params.get("token")
    if not token:
        return None
    try:
        return decode_token(token)
    except HTTPException:
        return None


# ─── Packet capture helpers (scapy) ───────────────────────────────────────────

def _get_capture_interfaces() -> list[dict]:
    """Return usable physical capture interfaces (skips virtual/loopback/VPN adapters)."""
    try:
        from scapy.arch.windows import get_windows_if_list
        seen, result = set(), []

        # Keywords in name OR description that indicate a virtual/software adapter
        SKIP = {
            # Loopback / null
            "Loopback", "Npcap Loopback",
            # Windows noise
            "WFP", "QoS", "NDIS", "Pseudo", "Teredo", "ISATAP", "6to4",
            "WAN Miniport", "PPTP", "L2TP", "IKEv2", "SSTP", "PPPOE", "Miniport",
            # Hyper-V / WSL / Docker virtual switches
            "vEthernet", "Hyper-V", "WSL", "Docker",
            # VMware / VirtualBox
            "VMware", "VirtualBox", "VBox",
            # VPN / overlay adapters
            "TAP", "TUN", "OpenVPN", "WireGuard", "Tailscale", "ZeroTier",
            "Hamachi", "NordVPN", "ExpressVPN", "Mullvad",
            # Generic "Virtual" label
            "Virtual",
        }

        def _should_skip(text: str) -> bool:
            tl = text.lower()
            return any(kw.lower() in tl for kw in SKIP)

        for iface in get_windows_if_list():
            name = iface.get("name", "")
            desc = iface.get("description", "")
            if _should_skip(name) or _should_skip(desc):
                continue
            # Only include adapters with a real IPv4 address
            ips = [ip for ip in iface.get("ips", [])
                   if ":" not in ip and not ip.startswith("127.") and ip != "0.0.0.0"]
            if not ips:
                continue
            key = tuple(sorted(ips))
            if key in seen:
                continue
            seen.add(key)
            result.append({"name": name, "description": desc, "ips": ips})

        return result
    except ImportError:
        return []


def _parse_packet(pkt) -> Optional[dict]:
    """Summarise a scapy packet into a JSON-serialisable dict."""
    try:
        from scapy.layers.inet import IP, TCP, UDP, ICMP
        from scapy.layers.inet6 import IPv6
        from scapy.layers.dns import DNS
        from scapy.layers.http import HTTP, HTTPRequest, HTTPResponse
        from scapy.all import ARP, Ether

        ts = time.time()
        length = len(pkt)
        src_mac = dst_mac = ""
        src_ip = dst_ip = ""
        sport = dport = None
        proto = "Other"
        info = ""
        color = "default"

        if pkt.haslayer(Ether):
            src_mac = pkt[Ether].src
            dst_mac = pkt[Ether].dst

        if pkt.haslayer(IP):
            src_ip = pkt[IP].src
            dst_ip = pkt[IP].dst
        elif pkt.haslayer(IPv6):
            src_ip = pkt[IPv6].src
            dst_ip = pkt[IPv6].dst

        if pkt.haslayer(TCP):
            sport = pkt[TCP].sport
            dport = pkt[TCP].dport
            flags = pkt[TCP].flags
            proto = "TCP"
            color = "tcp"
            # Detect common protocols by port
            ports = {sport, dport}
            if 80 in ports or 8080 in ports:
                proto = "HTTP"
                color = "http"
            elif 443 in ports or 8443 in ports:
                proto = "TLS"
                color = "tls"
            elif 22 in ports:
                proto = "SSH"
                color = "ssh"
            elif 53 in ports:
                proto = "DNS"
                color = "dns"
            flag_str = str(flags)
            info = f"{src_ip}:{sport} → {dst_ip}:{dport} [{flag_str}]"
        elif pkt.haslayer(UDP):
            sport = pkt[UDP].sport
            dport = pkt[UDP].dport
            proto = "UDP"
            color = "udp"
            ports = {sport, dport}
            if 53 in ports:
                proto = "DNS"
                color = "dns"
                if pkt.haslayer(DNS):
                    dns = pkt[DNS]
                    if dns.qr == 0 and dns.qd:
                        info = f"Query: {dns.qd.qname.decode(errors='replace').rstrip('.')}"
                    else:
                        info = f"Response ({dns.ancount} answers)"
            elif 67 in ports or 68 in ports:
                proto = "DHCP"
                color = "dhcp"
            info = info or f"{src_ip}:{sport} → {dst_ip}:{dport}"
        elif pkt.haslayer(ICMP):
            icmp = pkt[ICMP]
            proto = "ICMP"
            color = "icmp"
            t = {0: "Echo Reply", 8: "Echo Request", 3: "Dest Unreachable",
                 11: "Time Exceeded"}.get(icmp.type, f"Type {icmp.type}")
            info = f"{src_ip} → {dst_ip}: {t}"
        elif pkt.haslayer(ARP):
            arp = pkt[ARP]
            proto = "ARP"
            color = "arp"
            src_ip = arp.psrc
            dst_ip = arp.pdst
            op = "Who has" if arp.op == 1 else "Is at"
            info = f"{op} {dst_ip}? Tell {src_ip}"
        else:
            info = f"{src_ip} → {dst_ip}"

        if not info:
            info = f"{src_ip} → {dst_ip}"

        return {
            "ts": round(ts, 6),
            "src": src_ip,
            "dst": dst_ip,
            "sport": sport,
            "dport": dport,
            "proto": proto,
            "length": length,
            "info": info,
            "color": color,
            "src_mac": src_mac,
            "dst_mac": dst_mac,
        }
    except Exception:
        return None


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


# ─── Traffic capture WebSocket ────────────────────────────────────────────────

@router.websocket("/traffic")
async def traffic_ws(websocket: WebSocket):
    """
    Live packet capture stream (Wireshark-style).

    Query params:
      token      – JWT (required)
      iface      – interface name to capture on (optional, defaults to first LAN)
      filter     – BPF filter string (optional, e.g. "tcp port 443")
      max_pkts   – stop after N packets (optional, 0 = unlimited)

    Client can send JSON control messages:
      {"action": "stop"}
      {"action": "set_filter", "filter": "udp port 53"}

    Server sends:
      {"type": "interfaces", "interfaces": [...]}     – on connect
      {"type": "packet", ...packet fields...}          – per packet
      {"type": "stats", "total": N, "rate": N}        – every second
      {"type": "error", "message": "..."}
    """
    payload = _auth_ws(websocket)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    iface_name: Optional[str] = websocket.query_params.get("iface")
    bpf_filter: str = websocket.query_params.get("filter", "")
    max_pkts = int(websocket.query_params.get("max_pkts", "0"))

    # Send available interfaces immediately
    ifaces = _get_capture_interfaces()
    await websocket.send_text(json.dumps({"type": "interfaces", "interfaces": ifaces}))

    # Resolve interface name
    if not iface_name and ifaces:
        iface_name = ifaces[0]["name"]

    if not iface_name:
        await websocket.send_text(json.dumps({"type": "error", "message": "No capture interface available"}))
        await websocket.close()
        return

    # Queue bridges scapy thread → async WS
    pkt_queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
    stop_event = threading.Event()
    loop = asyncio.get_event_loop()
    total_captured = [0]
    rate_counter = [0]

    def _packet_callback(pkt):
        if stop_event.is_set():
            return True  # returning True stops scapy sniff
        parsed = _parse_packet(pkt)
        if parsed:
            total_captured[0] += 1
            rate_counter[0] += 1
            if not pkt_queue.full():
                loop.call_soon_threadsafe(pkt_queue.put_nowait, parsed)
        if max_pkts and total_captured[0] >= max_pkts:
            stop_event.set()
            return True

    def _sniff_thread():
        try:
            from scapy.all import sniff
            sniff(
                iface=iface_name,
                filter=bpf_filter or None,
                prn=_packet_callback,
                stop_filter=lambda _: stop_event.is_set(),
                store=False,
            )
        except Exception as e:
            loop.call_soon_threadsafe(
                pkt_queue.put_nowait,
                {"type": "error", "message": str(e)}
            )
        finally:
            loop.call_soon_threadsafe(pkt_queue.put_nowait, {"type": "_done"})

    sniff_thread = threading.Thread(target=_sniff_thread, daemon=True)
    sniff_thread.start()

    async def _read_client():
        """Handle control messages from client."""
        nonlocal bpf_filter
        try:
            while True:
                msg = await websocket.receive_text()
                try:
                    ctrl = json.loads(msg)
                    if ctrl.get("action") == "stop":
                        stop_event.set()
                        return
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            stop_event.set()

    # Start stats ticker
    async def _stats_ticker():
        while not stop_event.is_set():
            await asyncio.sleep(1)
            r = rate_counter[0]
            rate_counter[0] = 0
            try:
                await websocket.send_text(json.dumps({
                    "type": "stats",
                    "total_packets": total_captured[0],
                    "pps": r,
                    "iface": iface_name,
                    "filter": bpf_filter,
                }))
            except Exception:
                stop_event.set()
                return

    client_task = asyncio.create_task(_read_client())
    stats_task  = asyncio.create_task(_stats_ticker())

    try:
        while True:
            try:
                pkt = await asyncio.wait_for(pkt_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                # No packet in 5 s — keep alive unless capture was stopped
                if stop_event.is_set():
                    break
                continue  # ← keep waiting; do NOT exit the loop
            if pkt.get("type") == "_done":
                break
            if pkt.get("type") == "error":
                await websocket.send_text(json.dumps(pkt))
                break
            pkt["type"] = "packet"
            await websocket.send_text(json.dumps(pkt))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("Traffic WS error: %s", exc)
    finally:
        stop_event.set()
        client_task.cancel()
        stats_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("Traffic WS closed: iface=%s total=%d", iface_name, total_captured[0])


# ─── Live interfaces list (REST helper) ───────────────────────────────────────

@router.websocket("/discovery")
async def discovery_ws(websocket: WebSocket):
    """
    Real-time network discovery stream.

    Query params:
      token          – JWT (required)
      network_range  – CIDR to scan (optional, auto-detected if omitted)

    Server sends:
      {"type": "started",  "network_range": "...", "total": N}
      {"type": "node",     "node": <NetworkNode dict>}   – one per host, saved to DB
      {"type": "done",     "total": N, "network_range": "..."}
      {"type": "error",    "message": "..."}
    """
    from ....models.network import NetworkNode as NetworkNodeModel
    from datetime import datetime

    payload = _auth_ws(websocket)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    network_range: Optional[str] = websocket.query_params.get("network_range") or None

    try:
        # Host-agent full multi-method scan (scapy ARP + nmap + ping sweep) ~20-30s
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{HOST_AGENT_URL}/discover",
                json={"network_range": network_range},
            )
            data = resp.json()

        nr = data.get("network_range", network_range or "unknown")
        nodes_raw = data.get("nodes", [])

        await websocket.send_text(json.dumps({
            "type": "started",
            "network_range": nr,
            "total": len(nodes_raw),
        }))

        # ── Save each node to DB and stream proper NetworkNode dicts ──────────
        db: Session = SessionLocal()
        try:
            found_ips = {n.get("ip") for n in nodes_raw if n.get("ip")}
            # Mark previously-seen nodes on this range as inactive if not found now
            if found_ips:
                db.query(NetworkNodeModel).filter(
                    NetworkNodeModel.network_range == nr,
                    ~NetworkNodeModel.ip_address.in_(found_ips),
                ).update({"status": "inactive"}, synchronize_session=False)

            for i, n in enumerate(nodes_raw):
                ip = n.get("ip")
                if not ip:
                    continue

                node = (
                    db.query(NetworkNodeModel)
                    .filter(NetworkNodeModel.ip_address == ip)
                    .first()
                )
                if node:
                    node.mac_address = n.get("mac") or node.mac_address
                    node.hostname    = n.get("hostname") or node.hostname
                    node.device_type = n.get("device_type") or node.device_type
                    node.status      = "active"
                    node.last_seen_at = datetime.utcnow()
                else:
                    node = NetworkNodeModel(
                        ip_address   = ip,
                        mac_address  = n.get("mac"),
                        hostname     = n.get("hostname"),
                        device_type  = n.get("device_type", "unknown"),
                        network_range= nr,
                        status       = "active",
                        last_seen_at = datetime.utcnow(),
                    )
                    db.add(node)

                db.flush()

                node_dict = {
                    "id":                  str(node.id),
                    "ip_address":          node.ip_address,
                    "mac_address":         node.mac_address,
                    "hostname":            node.hostname,
                    "os_family":           node.os_family,
                    "os_version":          node.os_version,
                    "device_type":         node.device_type,
                    "open_ports":          node.open_ports or [],
                    "services":            node.services or [],
                    "status":              node.status,
                    "network_range":       node.network_range,
                    "risk_score":          node.risk_score or 0,
                    "first_discovered_at": node.first_discovered_at.isoformat() if node.first_discovered_at else None,
                    "last_seen_at":        node.last_seen_at.isoformat() if node.last_seen_at else None,
                }
                await websocket.send_text(json.dumps({"type": "node", "node": node_dict, "index": i}))
                await asyncio.sleep(0.02)

            db.commit()
        finally:
            db.close()

        await websocket.send_text(json.dumps({
            "type": "done",
            "total": len(nodes_raw),
            "network_range": nr,
        }))
        await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("Discovery WS error: %s", exc)
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
            await websocket.close()
        except Exception:
            pass
