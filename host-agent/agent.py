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
    """Parse ipconfig /all to find the first private LAN subnet."""
    try:
        out = subprocess.check_output(["ipconfig", "/all"], text=True, timeout=10)
        current_ip = None
        current_mask = None
        for line in out.splitlines():
            line = line.strip()
            ip_match = re.search(r"IPv4 Address.*?:\s*([\d.]+)", line)
            mask_match = re.search(r"Subnet Mask.*?:\s*([\d.]+)", line)
            if ip_match:
                current_ip = ip_match.group(1).rstrip("(Preferred)")
            if mask_match:
                current_mask = mask_match.group(1)
            if current_ip and current_mask and _is_private(current_ip):
                try:
                    net = ipaddress.IPv4Network(f"{current_ip}/{current_mask}", strict=False)
                    return str(net)
                except ValueError:
                    current_ip = current_mask = None
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


def _discover_arp() -> List[Dict]:
    """Quick discovery using the OS ARP cache — zero extra tools needed."""
    nodes: Dict[str, Dict] = {}
    try:
        out = subprocess.check_output(["arp", "-a"], text=True, timeout=10)
        for line in out.splitlines():
            # Windows:  192.168.1.1   aa-bb-cc-dd-ee-ff  dynamic
            # Linux:    ? (192.168.1.1) at aa:bb:cc:dd:ee:ff ...
            ip_match  = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
            mac_match = re.search(r"([\da-fA-F]{2}[:\-]){5}[\da-fA-F]{2}", line)
            if not ip_match:
                continue
            ip = ip_match.group(1)
            if not _is_private(ip):
                continue
            # Skip broadcast / multicast
            last_octet = int(ip.split(".")[-1])
            if last_octet in (0, 255) or ip.startswith("224."):
                continue
            mac = mac_match.group(0).replace("-", ":").lower() if mac_match else None
            if mac in ("ff:ff:ff:ff:ff:ff", None) or mac and mac.startswith("01:"):
                mac = None
            nodes[ip] = {"ip": ip, "mac": mac, "hostname": None}
    except Exception:
        pass
    return list(nodes.values())


def _resolve_hostnames(nodes: List[Dict]) -> None:
    """Parallel reverse DNS — all hosts resolved concurrently with 1s timeout each."""
    socket.setdefaulttimeout(1.0)

    def _resolve(node: Dict) -> None:
        try:
            node["hostname"] = socket.gethostbyaddr(node["ip"])[0]
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=min(32, len(nodes) or 1)) as pool:
        list(pool.map(_resolve, nodes))

    socket.setdefaulttimeout(None)


def _discover_nmap(network_range: str) -> List[Dict]:
    """Full ping-sweep with nmap — richer but requires nmap on PATH."""
    nodes: Dict[str, Dict] = {}
    cmd = [
        "nmap", "-sn",
        "-PE", "-PP",
        "-PS22,80,443,3389",
        "-PA80,443",
        "-T4", "--host-timeout", "20s",
        "--min-parallelism", "10",
        "-oX", "-",
        network_range,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
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
        pass  # nmap not installed
    except Exception:
        pass
    return list(nodes.values())


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
    network_range = body.network_range or detect_subnet()
    if not network_range:
        network_range = "192.168.1.0/24"  # safe fallback

    gateway_ip = _get_gateway()

    # ARP is instant — use it for discovery. Nmap is reserved for deep per-host scanning.
    raw_nodes = _discover_arp()
    _resolve_hostnames(raw_nodes)
    method = "arp"

    nodes = [
        NodeResult(
            ip=n["ip"],
            mac=n.get("mac"),
            hostname=n.get("hostname"),
            device_type=_classify_device(
                n["ip"], n.get("mac"), n.get("hostname"), gateway_ip
            ),
        )
        for n in raw_nodes
    ]

    return DiscoverResponse(network_range=network_range, nodes=nodes, method=method)


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


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 52)
    print(" VAPT Host Discovery Agent")
    print(" Listening on http://localhost:9999")
    print(" Accessible from Docker via host.docker.internal:9999")
    print(" Press Ctrl+C to stop")
    print("=" * 52)
    uvicorn.run(app, host="0.0.0.0", port=9999, log_level="warning")
