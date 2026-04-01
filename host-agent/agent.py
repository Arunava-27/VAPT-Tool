"""
VAPT Platform — Host Discovery Agent
Runs natively on the Windows/Linux/Mac host (NOT inside Docker).
Exposes a tiny HTTP API on localhost:9999 so the API Gateway
(reachable via host.docker.internal) can trigger real LAN discovery.

Start: python agent.py   or double-click start-host-agent.bat
"""

import os
import re
import socket
import asyncio
import subprocess
import ipaddress
import platform
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="VAPT Host Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Models ──────────────────────────────────────────────────────────────────

class DiscoverRequest(BaseModel):
    network_range: Optional[str] = None


class NodeResult(BaseModel):
    ip: str
    mac: Optional[str] = None
    hostname: Optional[str] = None
    device_type: str = "unknown"


class DiscoverResponse(BaseModel):
    network_range: str
    nodes: List[NodeResult]
    method: str  # "arp" | "nmap" | "arp+nmap"


# ─── Subnet detection ────────────────────────────────────────────────────────

PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in PRIVATE_NETS)
    except ValueError:
        return False


def _detect_subnet_windows() -> Optional[str]:
    """
    Parse ipconfig /all to find the best LAN subnet.
    Priority: prefer /24 networks on physical adapters, skip WSL/Docker/VPN/Hyper-V.
    """
    VIRTUAL_KEYWORDS = {"wsl", "docker", "hyper-v", "virtual", "loopback",
                        "vpn", "tap", "tun", "miniport", "teredo", "6to4",
                        "isatap", "vethernet"}
    try:
        out = subprocess.check_output(["ipconfig", "/all"], text=True, timeout=10)
        candidates = []     # list of (prefix_len, ip, mask, adapter_name)
        adapter_name = ""
        current_ip = current_mask = None
        is_virtual = False
        for line in out.splitlines():
            stripped = line.strip()
            # Detect new adapter block
            if line and not line.startswith(" ") and ":" in line:
                # Save previous adapter's candidate
                if current_ip and current_mask and _is_private(current_ip) and not is_virtual:
                    try:
                        net = ipaddress.IPv4Network(f"{current_ip}/{current_mask}", strict=False)
                        candidates.append((net.prefixlen, current_ip, current_mask, adapter_name, net))
                    except ValueError:
                        pass
                adapter_name = line.strip().rstrip(":")
                is_virtual = any(k in adapter_name.lower() for k in VIRTUAL_KEYWORDS)
                current_ip = current_mask = None
            ip_match   = re.search(r"IPv4 Address.*?:\s*([\d.]+)", stripped)
            mask_match = re.search(r"Subnet Mask.*?:\s*([\d.]+)", stripped)
            if ip_match:
                current_ip = ip_match.group(1).replace("(Preferred)", "").strip()
            if mask_match:
                current_mask = mask_match.group(1)
        # Last adapter
        if current_ip and current_mask and _is_private(current_ip) and not is_virtual:
            try:
                net = ipaddress.IPv4Network(f"{current_ip}/{current_mask}", strict=False)
                candidates.append((net.prefixlen, current_ip, current_mask, adapter_name, net))
            except ValueError:
                pass

        if not candidates:
            return None

        # Prefer larger prefix (more specific network), prioritize /24
        # Sort: prefer /24 (=best), then larger prefixlen, skip gigantic nets
        def _score(c):
            pl = c[0]
            if pl == 24:
                return 0       # perfect
            if pl > 24:
                return 1       # smaller subnet, fine
            if pl >= 20:
                return 2       # medium, acceptable
            return 3           # huge, last resort

        candidates.sort(key=lambda c: (_score(c), -(c[0])))
        best = candidates[0]
        return str(best[4])
    except Exception:
        pass
    return None


def _detect_subnet_linux() -> Optional[str]:
    """Use `ip route` to find the first private LAN route."""
    try:
        out = subprocess.check_output(["ip", "route"], text=True, timeout=10)
        for line in out.splitlines():
            parts = line.split()
            if parts and "/" in parts[0]:
                net_str = parts[0]
                try:
                    net = ipaddress.ip_network(net_str, strict=False)
                    if any(net.overlaps(p) for p in PRIVATE_NETS):
                        return str(net)
                except ValueError:
                    pass
    except Exception:
        pass
    return None


def detect_subnet() -> Optional[str]:
    if platform.system() == "Windows":
        return _detect_subnet_windows()
    return _detect_subnet_linux()


# ─── Device classification ────────────────────────────────────────────────────

ROUTER_OUI = {"00:50:56", "00:0c:29", "00:1a:a0", "b8:27:eb", "dc:a6:32",
               "00:1d:60", "00:17:f2", "e8:94:f6", "c8:d7:19", "84:16:f9"}
MOBILE_KEYWORDS = {"iphone", "android", "pixel", "galaxy", "phone", "mobile"}
ROUTER_KEYWORDS = {"router", "gateway", "gw", "rt-", "asus", "tp-link",
                   "netgear", "linksys", "dlink", "mikrotik", "ubiquiti", "unifi"}
SERVER_KEYWORDS = {"server", "nas", "synology", "qnap", "plex", "ubuntu",
                   "debian", "centos", "proxmox", "esxi", "vmware"}
PRINTER_KEYWORDS = {"printer", "hp", "canon", "epson", "brother", "ricoh"}
CAMERA_KEYWORDS  = {"cam", "camera", "nvr", "dvr", "hikvision", "dahua"}


def _classify_device(ip: str, mac: Optional[str], hostname: Optional[str],
                     gateway_ip: Optional[str]) -> str:
    if gateway_ip and ip == gateway_ip:
        return "router"
    hn = (hostname or "").lower()
    mac_prefix = (mac or "")[:8].lower()
    if any(k in hn for k in ROUTER_KEYWORDS):
        return "router"
    if any(k in hn for k in SERVER_KEYWORDS):
        return "server"
    if any(k in hn for k in MOBILE_KEYWORDS):
        return "mobile"
    if any(k in hn for k in PRINTER_KEYWORDS):
        return "printer"
    if any(k in hn for k in CAMERA_KEYWORDS):
        return "camera"
    if mac_prefix in ROUTER_OUI:
        return "router"
    return "pc"


# ─── Discovery methods ────────────────────────────────────────────────────────

def _get_gateway() -> Optional[str]:
    try:
        if platform.system() == "Windows":
            out = subprocess.check_output(["ipconfig"], text=True, timeout=5)
            for line in out.splitlines():
                m = re.search(r"Default Gateway.*?:\s*([\d.]+)", line.strip())
                if m and _is_private(m.group(1)):
                    return m.group(1)
        else:
            out = subprocess.check_output(["ip", "route"], text=True, timeout=5)
            for line in out.splitlines():
                if line.startswith("default"):
                    parts = line.split()
                    if len(parts) >= 3:
                        return parts[2]
    except Exception:
        pass
    return None


def _all_hosts(network_range: str) -> List[str]:
    """Enumerate all host IPs in a network range (skip network/broadcast).
    Capped at /20 (4094) for safety; active ping sweep only runs on /24 or smaller.
    """
    try:
        net = ipaddress.IPv4Network(network_range, strict=False)
        if net.num_addresses > 65536:
            return []
        # Cap active sweep at 254 hosts (/24); larger nets rely on scapy+nmap
        if net.num_addresses > 256:
            return []
        return [str(h) for h in net.hosts()]
    except ValueError:
        return []


def _all_lan_ranges() -> List[str]:
    """Return all private /24 ranges from all physical adapters (multi-homed support)."""
    ranges = []
    VIRTUAL_KEYWORDS = {"wsl", "docker", "hyper-v", "virtual", "loopback",
                        "vpn", "tap", "tun", "miniport", "teredo", "6to4",
                        "isatap", "vethernet"}
    try:
        if platform.system() == "Windows":
            out = subprocess.check_output(["ipconfig", "/all"], text=True, timeout=10)
            adapter_name = ""
            is_virtual = False
            for line in out.splitlines():
                stripped = line.strip()
                if line and not line.startswith(" ") and ":" in line:
                    adapter_name = line.strip().rstrip(":")
                    is_virtual = any(k in adapter_name.lower() for k in VIRTUAL_KEYWORDS)
                ip_m   = re.search(r"IPv4 Address.*?:\s*([\d.]+)", stripped)
                mask_m = re.search(r"Subnet Mask.*?:\s*([\d.]+)", stripped)
                if ip_m and mask_m and not is_virtual:
                    ip = ip_m.group(1).replace("(Preferred)", "").strip()
                    mask = mask_m.group(1)
                    if _is_private(ip):
                        try:
                            net = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
                            if net.prefixlen <= 24:
                                # Normalise to /24 for scanning
                                net24 = ipaddress.IPv4Network(f"{ip}/24", strict=False)
                                s = str(net24)
                                if s not in ranges:
                                    ranges.append(s)
                        except ValueError:
                            pass
        else:
            out = subprocess.check_output(["ip", "-4", "addr", "show"], text=True, timeout=10)
            for line in out.splitlines():
                m = re.search(r"inet\s+([\d.]+)/(\d+).*scope\s+global", line)
                if m:
                    ip, pl = m.group(1), int(m.group(2))
                    if _is_private(ip) and pl <= 24:
                        net = ipaddress.IPv4Network(f"{ip}/24", strict=False)
                        s = str(net)
                        if s not in ranges:
                            ranges.append(s)
    except Exception:
        pass
    return ranges


def _discover_scapy_arp(network_range: str) -> List[Dict]:
    """
    Netdiscover-style active ARP scan — sends ARP who-has to EVERY IP in the
    subnet.  This is the most reliable way to find all LAN devices.
    Requires scapy + Npcap (Windows) or raw-socket access (Linux/root).
    """
    nodes: Dict[str, Dict] = {}
    try:
        from scapy.all import ARP, Ether, srp  # type: ignore
        pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=network_range)
        answered, _ = srp(pkt, timeout=2, verbose=0, retry=1)
        for _, rcv in answered:
            ip  = rcv[ARP].psrc
            mac = rcv[Ether].src.lower()
            if _is_private(ip) and mac not in ("ff:ff:ff:ff:ff:ff",):
                nodes[ip] = {"ip": ip, "mac": mac, "hostname": None}
    except Exception:
        pass
    return list(nodes.values())


def _ping_one(ip: str) -> bool:
    """Single ICMP ping — returns True if host responds."""
    try:
        if platform.system() == "Windows":
            r = subprocess.run(
                ["ping", "-n", "1", "-w", "500", ip],
                capture_output=True, timeout=2
            )
            return r.returncode == 0
        else:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "1", ip],
                capture_output=True, timeout=2
            )
            return r.returncode == 0
    except Exception:
        return False


def _tcp_probe(ip: str, ports: List[int] = (80, 443, 22, 445, 3389),
               timeout: float = 0.5) -> bool:
    """Try TCP connect on common ports — catches hosts that block ICMP."""
    for port in ports:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except (ConnectionRefusedError, OSError):
            # ConnectionRefused means host IS up (it replied with RST)
            if isinstance(Exception, ConnectionRefusedError):
                return True
        except socket.timeout:
            pass
    return False


def _is_port_refused(ip: str, port: int, timeout: float = 0.4) -> bool:
    """A RST (connection refused) means the host is UP even if port is closed."""
    try:
        socket.create_connection((ip, port), timeout=timeout)
        return True
    except ConnectionRefusedError:
        return True   # host is alive — sent RST
    except Exception:
        return False


def _discover_ping_sweep(network_range: str) -> List[Dict]:
    """
    Parallel ICMP ping + TCP probe sweep — active host discovery without any
    extra tools.  Uses ThreadPoolExecutor to probe all hosts concurrently.
    """
    all_ips = _all_hosts(network_range)
    if not all_ips:
        return []

    found: Dict[str, Dict] = {}
    # Minimal set — RST on these means host is alive even if ICMP is blocked
    TCP_PROBE_PORTS = [80, 443, 445, 22, 3389]

    def _probe(ip: str) -> Optional[str]:
        if _ping_one(ip):
            return ip
        # TCP probes for ICMP-blocking hosts
        for port in TCP_PROBE_PORTS:
            if _is_port_refused(ip, port, timeout=0.2):
                return ip
        return None

    max_workers = min(256, len(all_ips))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for ip, alive in zip(all_ips, pool.map(_probe, all_ips)):
            if alive:
                found[ip] = {"ip": ip, "mac": None, "hostname": None}

    return list(found.values())


def _discover_nmap(network_range: str) -> List[Dict]:
    """
    nmap -sn ping sweep — most thorough host discovery.
    Uses ICMP echo/timestamp + TCP SYN to common ports.
    Runs as primary method when nmap is on PATH.
    """
    nodes: Dict[str, Dict] = {}
    cmd = [
        "nmap", "-sn",
        "-PE", "-PP", "-PM",                    # ICMP echo, timestamp, netmask
        "-PS21,22,23,25,80,110,443,445,3389",   # TCP SYN probes
        "-PA80,443,3389",                        # TCP ACK probes
        "-PU53,161",                             # UDP probes
        "-T4",
        "--host-timeout", "8s",
        "--min-parallelism", "100",
        "--min-rtt-timeout", "50ms",
        "--max-rtt-timeout", "300ms",
        "-oX", "-",
        network_range,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if not result.stdout.strip():
            return nodes
        root = ET.fromstring(result.stdout)
        for host in root.findall("host"):
            status = host.find("status")
            if status is None or status.get("state") != "up":
                continue
            addrs = {a.get("addrtype"): a.get("addr")
                     for a in host.findall("address")}
            ip = addrs.get("ipv4")
            if not ip or not _is_private(ip):
                continue
            mac = addrs.get("mac")
            hostname_el = host.find(".//hostname")
            hostname = hostname_el.get("name") if hostname_el is not None else None
            nodes[ip] = {"ip": ip, "mac": mac, "hostname": hostname}
    except FileNotFoundError:
        pass  # nmap not on PATH
    except Exception:
        pass
    return list(nodes.values())


def _discover_arp_cache() -> List[Dict]:
    """Supplement results with the OS ARP cache (zero-cost, instant)."""
    nodes: Dict[str, Dict] = {}
    try:
        out = subprocess.check_output(["arp", "-a"], text=True, timeout=10)
        for line in out.splitlines():
            ip_match  = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
            mac_match = re.search(r"([\da-fA-F]{2}[:\-]){5}[\da-fA-F]{2}", line)
            if not ip_match:
                continue
            ip = ip_match.group(1)
            if not _is_private(ip):
                continue
            last_octet = int(ip.split(".")[-1])
            if last_octet in (0, 255) or ip.startswith("224."):
                continue
            mac = mac_match.group(0).replace("-", ":").lower() if mac_match else None
            if mac in ("ff:ff:ff:ff:ff:ff",):
                mac = None
            if mac and mac.startswith("01:"):
                mac = None
            nodes[ip] = {"ip": ip, "mac": mac, "hostname": None}
    except Exception:
        pass
    return list(nodes.values())


def _enrich_mac_from_arp(nodes_map: Dict[str, Dict]) -> None:
    """Fill in missing MACs from ARP cache for already-found IPs."""
    cache = {n["ip"]: n for n in _discover_arp_cache()}
    for ip, node in nodes_map.items():
        if not node.get("mac") and ip in cache and cache[ip].get("mac"):
            node["mac"] = cache[ip]["mac"]


def _nbtscan(network_range: str) -> Dict[str, str]:
    """
    NetBIOS name resolution via nbtstat (Windows only) — gives Windows
    machine names for IPs that don't have DNS PTR records.
    Returns {ip: netbios_name}.
    """
    names: Dict[str, str] = {}
    if platform.system() != "Windows":
        return names
    all_ips = _all_hosts(network_range)[:254]  # cap for speed

    def _nbt(ip: str) -> Optional[tuple]:
        try:
            r = subprocess.run(
                ["nbtstat", "-A", ip],
                capture_output=True, text=True, timeout=2
            )
            for line in r.stdout.splitlines():
                # Lines like:  DESKTOP-ABC    <00>  UNIQUE  Registered
                m = re.match(r"\s+(\S+)\s+<00>\s+UNIQUE", line)
                if m:
                    return (ip, m.group(1))
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=min(50, len(all_ips) or 1)) as pool:
        for res in pool.map(_nbt, all_ips):
            if res:
                names[res[0]] = res[1]
    return names


def _resolve_hostnames(nodes: List[Dict]) -> None:
    """Parallel reverse DNS — all hosts resolved concurrently with 1s timeout."""
    socket.setdefaulttimeout(1.0)

    def _resolve(node: Dict) -> None:
        if node.get("hostname"):
            return
        try:
            node["hostname"] = socket.gethostbyaddr(node["ip"])[0]
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=min(64, len(nodes) or 1)) as pool:
        list(pool.map(_resolve, nodes))

    socket.setdefaulttimeout(None)


# ─── Interface enumeration ───────────────────────────────────────────────────

def _enumerate_interfaces() -> list:
    """Return all IPv4 interfaces on this host."""
    ifaces = []
    if platform.system() == "Windows":
        try:
            out = subprocess.check_output(["ipconfig", "/all"], text=True, timeout=10)
            adapter_name = "unknown"
            for line in out.splitlines():
                if line and not line.startswith(" ") and ":" in line:
                    adapter_name = line.strip().rstrip(":")
                line = line.strip()
                ip_match = re.search(r"IPv4 Address.*?:\s*([\d.]+)", line)
                mask_match = re.search(r"Subnet Mask.*?:\s*([\d.]+)", line)
                if ip_match:
                    ip = ip_match.group(1).replace("(Preferred)", "").strip()
                    _pending_ip = ip
                    ifaces.append({"interface": adapter_name, "ip": _pending_ip,
                                   "is_private": _is_private(_pending_ip)})
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(["ip", "-4", "addr", "show"], text=True, timeout=10)
            for line in out.splitlines():
                m = re.search(r"inet\s+([\d.]+)/(\d+).*scope\s+global\s+(\S+)", line)
                if m:
                    ip = m.group(1)
                    ifaces.append({"interface": m.group(3), "ip": ip,
                                   "is_private": _is_private(ip)})
        except Exception:
            pass
    # Deduplicate by IP
    seen: set = set()
    result = []
    for i in ifaces:
        if i["ip"] not in seen:
            seen.add(i["ip"])
            result.append(i)
    return result


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "platform": platform.system(),
        "hostname": socket.gethostname(),
        "version": "1.0.0",
    }


@app.get("/interfaces")
async def interfaces() -> Dict[str, Any]:
    """Return all IPv4 network interfaces of this host machine."""
    ifaces = _enumerate_interfaces()
    return {
        "hostname": socket.gethostname(),
        "platform": platform.system(),
        "interfaces": ifaces,
        "private_ips": [i["ip"] for i in ifaces if i.get("is_private")],
    }


@app.post("/discover", response_model=DiscoverResponse)
async def discover(body: DiscoverRequest) -> DiscoverResponse:
    # If caller specifies a range use it; otherwise scan ALL detected LAN ranges
    if body.network_range:
        ranges_to_scan = [body.network_range]
    else:
        ranges_to_scan = _all_lan_ranges()
        if not ranges_to_scan:
            primary = detect_subnet() or "192.168.1.0/24"
            ranges_to_scan = [primary]

    gateway_ip  = _get_gateway()
    merged: Dict[str, Dict] = {}
    methods_used: List[str] = []

    def _merge(results: List[Dict], method: str) -> None:
        if results and method not in methods_used:
            methods_used.append(method)
        for n in results:
            ip = n["ip"]
            if ip not in merged:
                merged[ip] = dict(n)
            else:
                if not merged[ip].get("mac") and n.get("mac"):
                    merged[ip]["mac"] = n["mac"]
                if not merged[ip].get("hostname") and n.get("hostname"):
                    merged[ip]["hostname"] = n["hostname"]

    loop = asyncio.get_event_loop()

    # ── Scan each detected range in parallel ─────────────────────────────────
    for net_range in ranges_to_scan:
        with ThreadPoolExecutor(max_workers=4) as pool:
            f_scapy = loop.run_in_executor(pool, _discover_scapy_arp,  net_range)
            f_nmap  = loop.run_in_executor(pool, _discover_nmap,       net_range)
            f_ping  = loop.run_in_executor(pool, _discover_ping_sweep, net_range)
            f_arp   = loop.run_in_executor(pool, _discover_arp_cache)

            try:
                scapy_r, nmap_r, ping_r, arp_r = await asyncio.wait_for(
                    asyncio.gather(f_scapy, f_nmap, f_ping, f_arp,
                                   return_exceptions=True),
                    timeout=90,
                )
            except asyncio.TimeoutError:
                scapy_r = nmap_r = ping_r = arp_r = []

        for res, label in [
            (scapy_r, "scapy-arp"),
            (nmap_r,  "nmap-sn"),
            (ping_r,  "ping-sweep"),
            (arp_r,   "arp-cache"),
        ]:
            if isinstance(res, list):
                _merge(res, label)

    if not methods_used:
        methods_used = ["none"]

    # ── Enrich MACs for ping/nmap-found hosts from ARP cache ─────────────────
    _enrich_mac_from_arp(merged)

    # ── Resolve hostnames in parallel (DNS) ───────────────────────────────────
    node_list = list(merged.values())
    _resolve_hostnames(node_list)

    # NetBIOS names only for already-found IPs (not a full sweep)
    if platform.system() == "Windows" and node_list:
        def _nbt_single(node: Dict) -> None:
            if node.get("hostname"):
                return
            try:
                r = subprocess.run(
                    ["nbtstat", "-A", node["ip"]],
                    capture_output=True, text=True, timeout=1
                )
                for line in r.stdout.splitlines():
                    m = re.match(r"\s+(\S+)\s+<00>\s+UNIQUE", line)
                    if m:
                        node["hostname"] = m.group(1)
                        break
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=min(30, len(node_list))) as pool:
            list(pool.map(_nbt_single, node_list))

    nodes = [
        NodeResult(
            ip=n["ip"],
            mac=n.get("mac"),
            hostname=n.get("hostname"),
            device_type=_classify_device(
                n["ip"], n.get("mac"), n.get("hostname"), gateway_ip
            ),
        )
        for n in node_list
    ]

    return DiscoverResponse(
        network_range=", ".join(ranges_to_scan),
        nodes=nodes,
        method="+".join(methods_used),
    )


class ScanNodeRequest(BaseModel):
    target: str
    profile: str = "quick"  # ping | quick | comprehensive | vuln


class ServiceResult(BaseModel):
    port: int
    protocol: str
    service: str
    product: str = ""
    version: str = ""


class VulnResult(BaseModel):
    vuln_id: str
    title: str
    severity: str
    description: str
    cve_id: Optional[str] = None
    cvss_score: Optional[float] = None
    port: Optional[int] = None
    protocol: Optional[str] = None
    service: Optional[str] = None
    evidence: Optional[str] = None


class ScanNodeResponse(BaseModel):
    target: str
    profile: str
    status: str
    open_ports: List[int]
    services: List[ServiceResult]
    os_family: Optional[str] = None
    os_version: Optional[str] = None
    vulnerabilities: List[VulnResult]


def _socket_scan(target: str, ports: List[int], timeout: float = 1.0) -> List[int]:
    """Pure-Python TCP connect scan — no nmap required."""
    open_ports = []
    for port in ports:
        try:
            with socket.create_connection((target, port), timeout=timeout):
                open_ports.append(port)
        except (ConnectionRefusedError, OSError, socket.timeout):
            pass
    return open_ports


COMMON_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445,
    465, 587, 993, 995, 1433, 1521, 2049, 2375, 3306, 3389,
    4444, 4848, 5432, 5900, 5985, 6379, 7001, 8080, 8443,
    8888, 9000, 9090, 9200, 9300, 27017,
]

SERVICE_MAP: Dict[int, str] = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp",
    53: "dns", 80: "http", 110: "pop3", 135: "msrpc",
    139: "netbios-ssn", 143: "imap", 443: "https",
    445: "microsoft-ds", 465: "smtps", 587: "smtp",
    993: "imaps", 995: "pop3s", 1433: "mssql", 1521: "oracle",
    2049: "nfs", 2375: "docker", 3306: "mysql", 3389: "rdp",
    4444: "metasploit", 5432: "postgresql", 5900: "vnc",
    5985: "winrm", 6379: "redis", 7001: "weblogic",
    8080: "http-alt", 8443: "https-alt", 8888: "jupyter",
    9000: "sonarqube", 9090: "prometheus", 9200: "elasticsearch",
    27017: "mongodb",
}


def _port_severity(port: int) -> str:
    """Assign severity based on port — dangerous services get higher severity."""
    if port in (23, 135, 139, 445, 1433, 1521, 4444, 5900, 2375):
        return "high"
    if port in (21, 22, 3306, 3389, 5432, 6379, 9200, 27017):
        return "medium"
    return "info"


def _extract_cves(script_output: str) -> List[Dict]:
    """Parse CVE IDs and CVSS scores from nmap script output."""
    findings = []
    lines = script_output.splitlines()
    for line in lines:
        cve_match = re.search(r"(CVE-\d{4}-\d+)", line)
        if not cve_match:
            continue
        cve_id = cve_match.group(1)
        cvss_match = re.search(r"(\d+\.\d+)\s*\(?(HIGH|CRITICAL|MEDIUM|LOW)?\)?", line, re.IGNORECASE)
        cvss_score = float(cvss_match.group(1)) if cvss_match else None
        severity = "info"
        if cvss_score:
            if cvss_score >= 9.0:
                severity = "critical"
            elif cvss_score >= 7.0:
                severity = "high"
            elif cvss_score >= 4.0:
                severity = "medium"
            else:
                severity = "low"
        findings.append({
            "cve_id": cve_id,
            "cvss_score": cvss_score,
            "severity": severity,
            "evidence": line.strip(),
        })
    return findings


@app.post("/scan-node", response_model=ScanNodeResponse)
async def scan_node(body: ScanNodeRequest) -> ScanNodeResponse:
    """Run nmap port/service/vuln scan on a single host. Requires nmap on PATH."""
    target = body.target
    profile = body.profile

    if profile == "ping":
        # Ping sweep — just check if host is alive, no port scan
        cmd = ["nmap", "-sn", "-T4", "--host-timeout", "20s", "-oX", "-", target]
        timeout = 30
    elif profile == "quick":
        cmd = ["nmap", "-F", "-T4", "-sV", "--host-timeout", "60s", "-oX", "-", target]
        timeout = 90
    elif profile == "vuln":
        cmd = ["nmap", "-sV", "-T4", "--script", "vulners,vuln", "-p-",
               "--host-timeout", "300s", "-oX", "-", target]
        timeout = 360
    else:  # comprehensive
        cmd = ["nmap", "-A", "-T4", "--host-timeout", "180s", "-oX", "-", target]
        timeout = 220

    open_ports: List[int] = []
    services: List[ServiceResult] = []
    vulnerabilities: List[VulnResult] = []
    os_family: Optional[str] = None
    os_version: Optional[str] = None

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        xml_out = result.stdout
        if not xml_out:
            raise ValueError("empty nmap output")

        root = ET.fromstring(xml_out)
        for host in root.findall("host"):
            ports_el = host.find("ports")
            if ports_el:
                for port_el in ports_el.findall("port"):
                    state = port_el.find("state")
                    if state is None or state.get("state") != "open":
                        continue
                    portid = int(port_el.get("portid", 0))
                    proto = port_el.get("protocol", "tcp")
                    svc_el = port_el.find("service")
                    svc_name = svc_el.get("name", "") if svc_el is not None else ""
                    svc_product = svc_el.get("product", "") if svc_el is not None else ""
                    svc_version = svc_el.get("version", "") if svc_el is not None else ""
                    open_ports.append(portid)
                    services.append(ServiceResult(
                        port=portid, protocol=proto,
                        service=svc_name, product=svc_product, version=svc_version,
                    ))
                    # Parse script output for CVEs
                    for script_el in port_el.findall("script"):
                        script_id = script_el.get("id", "")
                        output = script_el.get("output", "")
                        cves = _extract_cves(output)
                        for cve in cves:
                            vulnerabilities.append(VulnResult(
                                vuln_id=f"{cve['cve_id']}-{portid}",
                                title=f"{cve['cve_id']} on {svc_name}/{portid}",
                                severity=cve["severity"],
                                description=f"Script '{script_id}' detected {cve['cve_id']}",
                                cve_id=cve["cve_id"],
                                cvss_score=cve["cvss_score"],
                                port=portid,
                                protocol=proto,
                                service=svc_name,
                                evidence=cve["evidence"],
                            ))
                    # Info-level finding for every open port
                    vulnerabilities.append(VulnResult(
                        vuln_id=f"port-{portid}-{proto}",
                        title=f"Open Port: {svc_name or 'unknown'} on {portid}/{proto}",
                        severity="info",
                        description=f"{svc_product} {svc_version}".strip() or f"Port {portid}/{proto} is open",
                        port=portid, protocol=proto, service=svc_name,
                    ))

            os_el = host.find("os")
            if os_el:
                match_el = os_el.find(".//osmatch")
                if match_el is not None:
                    os_version = match_el.get("name")
                    osclass = match_el.find("osclass")
                    if osclass is not None:
                        os_family = osclass.get("osfamily")

    except FileNotFoundError:
        # ── nmap not installed — fallback to Python socket scanner ─────────
        if profile == "ping":
            # Ping fallback: try TCP connect on port 80 or 443
            loop = asyncio.get_event_loop()
            raw_open = await loop.run_in_executor(
                None, lambda: _socket_scan(target, [80, 443, 22], timeout=1.5)
            )
            status_str = "completed" if raw_open else "host-unreachable"
            return ScanNodeResponse(
                target=target, profile=profile, status=status_str,
                open_ports=[], services=[], vulnerabilities=[],
            )
        loop = asyncio.get_event_loop()
        raw_open = await loop.run_in_executor(
            None, lambda: _socket_scan(target, COMMON_PORTS, timeout=0.8)
        )
        for portid in raw_open:
            svc_name = SERVICE_MAP.get(portid, "unknown")
            open_ports.append(portid)
            services.append(ServiceResult(port=portid, protocol="tcp", service=svc_name))
            vulnerabilities.append(VulnResult(
                vuln_id=f"port-{portid}-tcp",
                title=f"Open Port: {svc_name} on {portid}/tcp",
                severity=_port_severity(portid),
                description=f"Port {portid}/tcp ({svc_name}) is open",
                port=portid, protocol="tcp", service=svc_name,
            ))
        return ScanNodeResponse(
            target=target, profile=profile, status="completed",
            open_ports=open_ports, services=services, vulnerabilities=vulnerabilities,
        )
    except subprocess.TimeoutExpired:
        return ScanNodeResponse(target=target, profile=profile, status="timeout",
                                open_ports=open_ports, services=services, vulnerabilities=vulnerabilities)
    except Exception as e:
        return ScanNodeResponse(target=target, profile=profile, status=f"error: {e}",
                                open_ports=[], services=[], vulnerabilities=[])

    return ScanNodeResponse(
        target=target, profile=profile, status="completed",
        open_ports=open_ports, services=services,
        os_family=os_family, os_version=os_version,
        vulnerabilities=vulnerabilities,
    )


# ─── Worker monitoring ────────────────────────────────────────────────────────

import json as _json
import psutil
from pathlib import Path
from fastapi.responses import StreamingResponse

_WORKERS_DIR = Path(__file__).parent.parent / "workers"
_PID_FILE    = _WORKERS_DIR / ".native-worker-pids.json"
_LOGS_DIR    = _WORKERS_DIR / "logs"

WORKER_META = {
    "nmap":       {"label": "Nmap Scanner",    "queue": "nmap",       "description": "Real LAN port & service discovery"},
    "trivy":      {"label": "Trivy Scanner",   "queue": "trivy",      "description": "Container & image vulnerability scanning"},
    "prowler":    {"label": "Prowler Scanner", "queue": "prowler",    "description": "Cloud security posture assessment"},
    "zap":        {"label": "OWASP ZAP",       "queue": "zap",        "description": "Web application vulnerability scanning"},
    "metasploit": {"label": "Metasploit",      "queue": "metasploit", "description": "Exploitation framework & testing"},
}


def _read_pids() -> Dict[str, int]:
    try:
        if _PID_FILE.exists():
            return _json.loads(_PID_FILE.read_text())
    except Exception:
        pass
    return {}


def _process_alive(pid: int) -> bool:
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except Exception:
        return False


def _process_stats(pid: int) -> Dict[str, Any]:
    try:
        p = psutil.Process(pid)
        with p.oneshot():
            return {
                "cpu_percent": p.cpu_percent(interval=0.1),
                "memory_mb": round(p.memory_info().rss / 1024 / 1024, 1),
                "threads": p.num_threads(),
                "status": p.status(),
                "create_time": p.create_time(),
            }
    except Exception:
        return {}


def _tail_log(path: Path, lines: int = 100) -> List[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return text.splitlines()[-lines:]
    except Exception:
        return []


@app.get("/workers/status")
def get_workers_status():
    """Return status of all native Celery workers tracked by PID file."""
    pids = _read_pids()
    result = []
    for name, meta in WORKER_META.items():
        pid = pids.get(name)
        alive = _process_alive(pid) if pid else False
        stats = _process_stats(pid) if (pid and alive) else {}
        log_file  = _LOGS_DIR / f"{name}.log"
        err_file  = _LOGS_DIR / f"{name}-err.log"
        last_lines = _tail_log(err_file, 5) if err_file.exists() else []
        result.append({
            "name": name,
            "label": meta["label"],
            "queue": meta["queue"],
            "description": meta["description"],
            "status": "running" if alive else ("stopped" if pid else "not_started"),
            "pid": pid,
            "alive": alive,
            "stats": stats,
            "log_file": str(log_file),
            "err_file": str(err_file),
            "last_log_lines": last_lines,
        })
    return result


@app.get("/workers/{name}/logs")
def get_worker_logs(name: str, tail: int = 200, stream: str = "stderr"):
    """Return recent log lines for a worker. stream=stdout|stderr|all"""
    if name not in WORKER_META:
        return {"error": f"Unknown worker: {name}", "lines": []}
    log_file = _LOGS_DIR / f"{name}.log"
    err_file = _LOGS_DIR / f"{name}-err.log"
    lines = []
    if stream in ("stdout", "all") and log_file.exists():
        lines += [{"stream": "stdout", "text": l} for l in _tail_log(log_file, tail)]
    if stream in ("stderr", "all") and err_file.exists():
        lines += [{"stream": "stderr", "text": l} for l in _tail_log(err_file, tail)]
    return {"worker": name, "lines": lines[-tail:], "total": len(lines)}


# ─── Self-management ──────────────────────────────────────────────────────────

import signal as _signal
import threading as _threading

@app.get("/agent/status")
def agent_status():
    """Return host-agent process info."""
    pid = os.getpid()
    try:
        p = psutil.Process(pid)
        with p.oneshot():
            return {
                "status": "online",
                "pid": pid,
                "uptime_s": round(psutil.time.time() - p.create_time()),
                "memory_mb": round(p.memory_info().rss / 1024 / 1024, 1),
                "cpu_percent": p.cpu_percent(interval=0.1),
                "version": "1.0.0",
                "port": 9999,
            }
    except Exception as exc:
        return {"status": "online", "pid": pid, "error": str(exc)}


@app.post("/agent/shutdown")
def agent_shutdown():
    """Gracefully shut down the host agent."""
    def _stop():
        import time
        time.sleep(0.5)
        os.kill(os.getpid(), _signal.SIGTERM)
    _threading.Thread(target=_stop, daemon=True).start()
    return {"ok": True, "message": "Host agent shutting down…"}


# ─── Service Management ───────────────────────────────────────────────────────

import time as _time

_PROJECT_ROOT = Path(__file__).parent.parent
_SERVICE_PID_FILE = _PROJECT_ROOT / ".service-pids.json"

_ENV_EXTRAS = {
    "DATABASE_URL": "postgresql://vapt_user:changeme123@localhost:5433/vapt_platform",
    "REDIS_URL": "redis://:redis123@localhost:6379/0",
    "RABBITMQ_URL": "amqp://guest:guest@localhost:5672/",
    "CELERY_BROKER_URL": "amqp://guest:guest@localhost:5672/",
    "CELERY_RESULT_BACKEND": "rpc://",
    "ELASTICSEARCH_URL": "http://localhost:9200",
    "MINIO_ENDPOINT": "localhost:9000",
    "MINIO_ACCESS_KEY": "minioadmin",
    "MINIO_SECRET_KEY": "minioadmin123",
    "SECRET_KEY": "supersecretkey-changeme",
    "JWT_SECRET_KEY": "supersecretkey-changeme",
    "CORS_ORIGINS": "http://localhost:3000,http://localhost:5173",
    "OLLAMA_BASE_URL": "http://localhost:11434",
}

_DOCKER_SERVICES = {
    "postgres":      {"label": "PostgreSQL",    "container": "vapt-postgres",       "category": "data",    "icon": "database"},
    "redis":         {"label": "Redis",          "container": "vapt-redis",          "category": "data",    "icon": "server"},
    "rabbitmq":      {"label": "RabbitMQ",       "container": "vapt-rabbitmq",       "category": "data",    "icon": "server"},
    "elasticsearch": {"label": "Elasticsearch",  "container": "vapt-elasticsearch",  "category": "data",    "icon": "search"},
    "minio":         {"label": "MinIO Storage",  "container": "vapt-minio",          "category": "data",    "icon": "storage"},
    "vault":         {"label": "Vault",          "container": "vapt-vault",          "category": "data",    "icon": "shield"},
    "ai-engine":     {"label": "AI Engine",      "container": "vapt-ai-engine",      "category": "backend", "icon": "cpu"},
    "ollama":        {"label": "Ollama LLM",     "container": "vapt-ollama",         "category": "backend", "icon": "cpu"},
}

_NATIVE_SERVICES = {
    "api-gateway": {
        "label": "API Gateway", "category": "backend", "port": 8000, "icon": "api",
        "cmd": [
            str(_PROJECT_ROOT / "api-gateway" / ".venv" / "Scripts" / "python.exe"),
            "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "app"
        ],
        "cwd": str(_PROJECT_ROOT / "api-gateway"),
        "log_file": str(_PROJECT_ROOT / "api-gateway" / "logs" / "api-gateway.log"),
    },
    "host-agent": {
        "label": "Host Agent", "category": "backend", "port": 9999, "icon": "agent", "self": True,
    },
}

_WORKER_CMD_BASE = ["-m", "celery", "-A", "app.tasks", "worker", "--loglevel=info", "--pool=solo", "--concurrency=1"]
_WORKER_SERVICES = {
    "worker-nmap":    {"label": "NMAP Worker",    "category": "worker", "queue": "nmap",    "icon": "scan",
                       "venv": str(_PROJECT_ROOT / "workers" / "nmap" / ".venv" / "Scripts" / "python.exe"),
                       "cwd": str(_PROJECT_ROOT / "workers" / "nmap"),
                       "log_file": str(_LOGS_DIR / "nmap.log")},
    "worker-trivy":   {"label": "Trivy Worker",   "category": "worker", "queue": "trivy",   "icon": "scan",
                       "venv": str(_PROJECT_ROOT / "workers" / "trivy" / ".venv" / "Scripts" / "python.exe"),
                       "cwd": str(_PROJECT_ROOT / "workers" / "trivy"),
                       "log_file": str(_LOGS_DIR / "trivy.log")},
    "worker-prowler": {"label": "Prowler Worker", "category": "worker", "queue": "prowler", "icon": "cloud",
                       "venv": str(_PROJECT_ROOT / "workers" / "prowler" / ".venv" / "Scripts" / "python.exe"),
                       "cwd": str(_PROJECT_ROOT / "workers" / "prowler"),
                       "log_file": str(_LOGS_DIR / "prowler.log")},
}


def _read_svc_pids() -> Dict[str, int]:
    try:
        if _SERVICE_PID_FILE.exists():
            return _json.loads(_SERVICE_PID_FILE.read_text())
    except Exception:
        pass
    return {}


def _write_svc_pids(pids: Dict[str, int]):
    try:
        _SERVICE_PID_FILE.write_text(_json.dumps(pids))
    except Exception:
        pass


def _docker_container_status(container: str) -> Dict[str, Any]:
    try:
        r = subprocess.run(
            ["docker", "inspect", container, "--format",
             "{{.State.Status}}|{{.State.StartedAt}}|{{.State.FinishedAt}}"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split("|")
            state = parts[0] if parts else "unknown"
            return {"status": "running" if state == "running" else "stopped", "state": state,
                    "started_at": parts[1] if len(parts) > 1 else None}
        return {"status": "stopped", "state": "not_found"}
    except Exception as e:
        return {"status": "unknown", "error": str(e)}


def _native_svc_info(name: str, pid: int) -> Dict[str, Any]:
    if pid and _process_alive(pid):
        stats = _process_stats(pid)
        uptime = int(_time.time() - stats.get("create_time", _time.time())) if "create_time" in stats else 0
        return {"status": "running", "pid": pid,
                "cpu_percent": stats.get("cpu_percent", 0),
                "memory_mb": stats.get("memory_mb", 0),
                "uptime_seconds": uptime}
    return {"status": "stopped", "pid": None}


def _get_worker_pid(queue: str) -> int:
    """Get PID of a native worker from existing worker PID file."""
    pids = _read_pids()
    return pids.get(queue)


def _write_worker_pid(queue: str, pid: int):
    pids = _read_pids()
    pids[queue] = pid
    try:
        _PID_FILE.write_text(_json.dumps(pids))
    except Exception:
        pass


def _remove_worker_pid(queue: str):
    pids = _read_pids()
    pids.pop(queue, None)
    try:
        _PID_FILE.write_text(_json.dumps(pids))
    except Exception:
        pass


@app.get("/services")
def list_all_services():
    """Return status of ALL platform services: Docker containers + native processes."""
    result = []

    # Docker services
    for name, meta in _DOCKER_SERVICES.items():
        ds = _docker_container_status(meta["container"])
        result.append({
            "id": name, "label": meta["label"], "category": meta["category"],
            "type": "docker", "icon": meta["icon"],
            "container": meta["container"],
            "status": ds["status"], "state": ds.get("state"),
            "started_at": ds.get("started_at"),
        })

    # Native services (api-gateway, host-agent)
    svc_pids = _read_svc_pids()
    for name, meta in _NATIVE_SERVICES.items():
        if meta.get("self"):
            pid = os.getpid()
        else:
            pid = svc_pids.get(name)
        info = _native_svc_info(name, pid)
        result.append({
            "id": name, "label": meta["label"], "category": meta["category"],
            "type": "native", "icon": meta["icon"],
            "port": meta.get("port"),
            "self": meta.get("self", False),
            **info,
        })

    # Worker services
    for name, meta in _WORKER_SERVICES.items():
        queue = meta["queue"]
        pid = _get_worker_pid(queue)
        info = _native_svc_info(name, pid)
        result.append({
            "id": name, "label": meta["label"], "category": meta["category"],
            "type": "worker", "icon": meta["icon"],
            "queue": queue,
            **info,
        })

    return result


@app.post("/services/{name}/start")
def start_service(name: str):
    """Start a service by name."""
    # Docker service
    if name in _DOCKER_SERVICES:
        meta = _DOCKER_SERVICES[name]
        r = subprocess.run(["docker", "start", meta["container"]], capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return {"ok": True, "message": f"{meta['label']} started"}
        return {"ok": False, "message": r.stderr.strip() or "Failed to start container"}

    # Native service (api-gateway)
    if name in _NATIVE_SERVICES:
        meta = _NATIVE_SERVICES[name]
        if meta.get("self"):
            return {"ok": False, "message": "Cannot start host-agent from itself"}
        svc_pids = _read_svc_pids()
        existing_pid = svc_pids.get(name)
        if existing_pid and _process_alive(existing_pid):
            return {"ok": False, "message": f"{meta['label']} is already running (PID {existing_pid})"}
        env = os.environ.copy()
        env.update(_ENV_EXTRAS)
        log_path = Path(meta["log_file"])
        log_path.parent.mkdir(parents=True, exist_ok=True)
        flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        with open(log_path, "a") as log_f:
            proc = subprocess.Popen(
                meta["cmd"], cwd=meta["cwd"], env=env,
                stdout=log_f, stderr=log_f,
                creationflags=flags
            )
        svc_pids[name] = proc.pid
        _write_svc_pids(svc_pids)
        _time.sleep(1)
        if _process_alive(proc.pid):
            return {"ok": True, "pid": proc.pid, "message": f"{meta['label']} started (PID {proc.pid})"}
        return {"ok": False, "message": f"{meta['label']} started but died immediately. Check logs."}

    # Worker service
    if name in _WORKER_SERVICES:
        meta = _WORKER_SERVICES[name]
        queue = meta["queue"]
        existing_pid = _get_worker_pid(queue)
        if existing_pid and _process_alive(existing_pid):
            return {"ok": False, "message": f"{meta['label']} is already running (PID {existing_pid})"}
        env = os.environ.copy()
        env.update(_ENV_EXTRAS)
        log_path = Path(meta["log_file"])
        log_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [meta["venv"]] + _WORKER_CMD_BASE + ["-Q", queue]
        flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        with open(log_path, "a") as log_f:
            proc = subprocess.Popen(cmd, cwd=meta["cwd"], env=env, stdout=log_f, stderr=log_f, creationflags=flags)
        _write_worker_pid(queue, proc.pid)
        _time.sleep(1)
        if _process_alive(proc.pid):
            return {"ok": True, "pid": proc.pid, "message": f"{meta['label']} started (PID {proc.pid})"}
        return {"ok": False, "message": f"{meta['label']} started but died immediately. Check logs."}

    return {"ok": False, "message": f"Unknown service: {name}"}


@app.post("/services/{name}/stop")
def stop_service(name: str):
    """Stop a service by name."""
    # Docker service
    if name in _DOCKER_SERVICES:
        meta = _DOCKER_SERVICES[name]
        r = subprocess.run(["docker", "stop", meta["container"]], capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return {"ok": True, "message": f"{meta['label']} stopped"}
        return {"ok": False, "message": r.stderr.strip() or "Failed to stop container"}

    # Native service (api-gateway)
    if name in _NATIVE_SERVICES:
        meta = _NATIVE_SERVICES[name]
        if meta.get("self"):
            return {"ok": False, "message": "Use the shutdown endpoint to stop host-agent"}
        svc_pids = _read_svc_pids()
        pid = svc_pids.get(name)
        if not pid or not _process_alive(pid):
            return {"ok": False, "message": f"{meta['label']} is not running"}
        try:
            proc = psutil.Process(pid)
            for child in proc.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
            proc.kill()
            svc_pids.pop(name, None)
            _write_svc_pids(svc_pids)
            return {"ok": True, "message": f"{meta['label']} stopped"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # Worker service
    if name in _WORKER_SERVICES:
        meta = _WORKER_SERVICES[name]
        queue = meta["queue"]
        pid = _get_worker_pid(queue)
        if not pid or not _process_alive(pid):
            return {"ok": False, "message": f"{meta['label']} is not running"}
        try:
            proc = psutil.Process(pid)
            for child in proc.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
            proc.kill()
            _remove_worker_pid(queue)
            return {"ok": True, "message": f"{meta['label']} stopped"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    return {"ok": False, "message": f"Unknown service: {name}"}


@app.get("/services/{name}/logs")
def get_service_logs(name: str, lines: int = 150):
    """Get recent log lines for a service."""
    log_file = None
    if name in _NATIVE_SERVICES and not _NATIVE_SERVICES[name].get("self"):
        log_file = Path(_NATIVE_SERVICES[name]["log_file"])
    elif name in _WORKER_SERVICES:
        log_file = Path(_WORKER_SERVICES[name]["log_file"])

    if not log_file:
        if name in _DOCKER_SERVICES:
            container = _DOCKER_SERVICES[name]["container"]
            r = subprocess.run(["docker", "logs", "--tail", str(lines), container],
                               capture_output=True, text=True, timeout=10)
            combined = (r.stdout + r.stderr).splitlines()
            return {"lines": [{"text": l, "stream": "stdout"} for l in combined if l.strip()]}
        return {"lines": [], "error": "No log file for this service"}

    raw_lines = _tail_log(log_file, lines)
    return {"lines": [{"text": l, "stream": "stdout"} for l in raw_lines]}


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 52)
    print(" VAPT Host Discovery Agent")
    print(" Listening on http://localhost:9999")
    print(" Accessible from Docker via host.docker.internal:9999")
    print(" Press Ctrl+C to stop")
    print("=" * 52)
    uvicorn.run(app, host="0.0.0.0", port=9999, log_level="warning")
