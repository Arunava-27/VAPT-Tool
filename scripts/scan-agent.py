#!/usr/bin/env python3
"""
VAPT Platform — Host Network Scanner Agent
==========================================
Run this script DIRECTLY on the machine connected to the target LAN
(NOT inside Docker). It scans the local network using nmap and pushes
results to the VAPT platform API.

Why this exists:
  Docker Desktop on Windows/macOS runs containers in a NAT'd VM, so the
  nmap worker inside Docker cannot reach your real LAN. This agent runs
  natively on the host where nmap has direct LAN access.

Requirements:
  pip install requests
  nmap must be installed on the host (https://nmap.org/download.html)

Usage examples:
  python scan-agent.py --user admin@vapt.tool --password yourpassword
  python scan-agent.py --user admin@vapt.tool --password yourpassword --range 192.168.1.0/24
  python scan-agent.py --url http://192.168.1.50:8000 --user admin@vapt.tool --password yourpassword
  python scan-agent.py --user admin@vapt.tool --password yourpassword --dry-run
"""

import argparse
import json
import re
import socket
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Optional

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package is required.  Run:  pip install requests")
    sys.exit(1)


# ─── Subnet auto-detection ────────────────────────────────────────────────────

def _prefix_from_mask(mask: str) -> int:
    return bin(struct.unpack(">I", socket.inet_aton(mask))[0]).count("1")


def _network_address(ip: str, prefix: int) -> str:
    ip_int  = struct.unpack(">I", socket.inet_aton(ip))[0]
    mask    = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return socket.inet_ntoa(struct.pack(">I", ip_int & mask))


def _is_private(ip: str) -> bool:
    return (
        ip.startswith("10.") or
        ip.startswith("192.168.") or
        bool(re.match(r"172\.(1[6-9]|2[0-9]|3[01])\.", ip))
    )


def _detect_linux() -> Optional[str]:
    try:
        import fcntl
        SIOCGIFADDR    = 0x8915
        SIOCGIFNETMASK = 0x891B
        with open("/proc/net/dev") as f:
            ifaces = [l.split(":")[0].strip() for l in f.readlines()[2:] if ":" in l]
        for iface in ifaces:
            if iface == "lo" or any(iface.startswith(p) for p in ("docker", "br-", "veth", "virbr")):
                continue
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            packed = struct.pack("256s", iface[:15].encode())
            try:
                ip_raw   = fcntl.ioctl(s.fileno(), SIOCGIFADDR,    packed)[20:24]
                mask_raw = fcntl.ioctl(s.fileno(), SIOCGIFNETMASK, packed)[20:24]
            except OSError:
                continue
            finally:
                s.close()
            ip     = socket.inet_ntoa(ip_raw)
            prefix = _prefix_from_mask(socket.inet_ntoa(mask_raw))
            if not _is_private(ip):
                continue
            return f"{_network_address(ip, prefix)}/{prefix}"
    except Exception:
        pass
    return None


def _detect_windows() -> Optional[str]:
    try:
        out = subprocess.run(["ipconfig", "/all"], capture_output=True, text=True, timeout=10).stdout
        SKIP = ("virtualbox", "vmware", "hyper-v", "wsl", "loopback", "bluetooth",
                "isatap", "teredo", "6to4", "vethernet", "tap-")
        current_adapter = ""
        cur_ip = cur_mask = None
        best: Optional[str] = None
        preferred: Optional[str] = None  # Wi-Fi preferred over wired

        for line in out.splitlines():
            # Adapter header lines are not indented
            if not line.startswith(" ") and "adapter" in line.lower():
                current_adapter = line.lower()
                cur_ip = cur_mask = None
                continue

            if any(kw in current_adapter for kw in SKIP):
                continue

            m = re.search(r"IPv4 Address.*?:\s*([\d.]+)", line)
            if m:
                cur_ip = m.group(1)
            m = re.search(r"Subnet Mask.*?:\s*([\d.]+)", line)
            if m:
                cur_mask = m.group(1)

            if cur_ip and cur_mask:
                if _is_private(cur_ip):
                    prefix = _prefix_from_mask(cur_mask)
                    subnet = f"{_network_address(cur_ip, prefix)}/{prefix}"
                    if any(kw in current_adapter for kw in ("wi-fi", "wireless", "wlan")):
                        preferred = subnet
                    elif best is None:
                        best = subnet
                cur_ip = cur_mask = None

        return preferred or best
    except Exception:
        pass
    return None


def auto_detect_subnet() -> str:
    subnet = _detect_linux() or _detect_windows()
    if not subnet:
        raise RuntimeError(
            "Could not auto-detect LAN subnet. "
            "Use --range (e.g. --range 192.168.1.0/24)"
        )
    return subnet


# ─── Device type classifier ───────────────────────────────────────────────────

VENDOR_KEYWORDS = {
    "apple": "mobile", "samsung": "mobile", "xiaomi": "mobile",
    "huawei": "mobile", "oppo": "mobile", "oneplus": "mobile",
    "cisco": "router",  "netgear": "router", "tp-link": "router",
    "d-link": "router", "asus": "router",   "ubiquiti": "router",
    "mikrotik": "router", "juniper": "router", "aruba": "router",
    "dell": "pc",   "lenovo": "pc",    "intel": "pc",
    "realtek": "pc", "hp": "pc",       "hewlett": "pc",
    "raspberry": "iot", "espressif": "iot", "arduino": "iot",
    "canon": "printer",  "epson": "printer", "brother": "printer",
    "xerox": "printer",
    "axis": "camera", "hikvision": "camera", "dahua": "camera",
}


def _guess_type(ip: str, mac: Optional[str], hostname: Optional[str],
                gateway_ips: set) -> str:
    if ip in gateway_ips:
        return "router"
    combined = f"{mac or ''} {hostname or ''}".lower()
    for kw, dtype in VENDOR_KEYWORDS.items():
        if kw in combined:
            return dtype
    if hostname:
        if re.search(r"\b(router|gateway|gw|ap|switch)\b", hostname, re.I):
            return "router"
        if re.search(r"\b(phone|iphone|android|mobile)\b", hostname, re.I):
            return "mobile"
        if re.search(r"\b(server|srv|nas|storage)\b", hostname, re.I):
            return "server"
        if re.search(r"\b(print|printer)\b", hostname, re.I):
            return "printer"
    return "pc"


# ─── nmap scan ────────────────────────────────────────────────────────────────

def scan_network(network_range: str) -> list[dict]:
    print(f"\n[*] Scanning {network_range} with nmap ...")

    cmd = [
        "nmap", "-sn",
        "-PE", "-PP",
        "-PS22,23,25,53,80,110,135,139,143,443,445,3389,5900,8080,8443",
        "-PA80,443,3389",
        "-PU53,67,137,161",
        "-T4",
        "--host-timeout", "30s",
        "--min-parallelism", "20",
        "--max-retries", "2",
        "-oX", "-",
        network_range,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        print("ERROR: nmap not found.")
        print("  Linux:   sudo apt install nmap  /  sudo yum install nmap")
        print("  Windows: https://nmap.org/download.html")
        sys.exit(1)

    if result.returncode != 0 and not result.stdout.strip():
        print(f"ERROR: nmap exited {result.returncode}:\n{result.stderr[:500]}")
        sys.exit(1)

    # Detect gateway IPs
    gateway_ips: set[str] = set()
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                parts = line.strip().split()
                if len(parts) >= 3 and parts[1] == "00000000":
                    gw = socket.inet_ntoa(bytes.fromhex(parts[2])[::-1])
                    if gw != "0.0.0.0":
                        gateway_ips.add(gw)
    except Exception:
        pass
    if not gateway_ips:
        base = network_range.split("/")[0].rsplit(".", 1)[0]
        gateway_ips = {f"{base}.1", f"{base}.254"}

    nodes: list[dict] = []
    try:
        root = ET.fromstring(result.stdout)
    except ET.ParseError:
        print("ERROR: Failed to parse nmap XML.")
        return []

    for host in root.findall("host"):
        status = host.find("status")
        if status is None or status.get("state") != "up":
            continue
        ip = mac = hostname = None
        for addr in host.findall("address"):
            if addr.get("addrtype") == "ipv4":
                ip = addr.get("addr")
            elif addr.get("addrtype") == "mac":
                mac = addr.get("addr")
        if not ip:
            continue
        hn_el = host.find(".//hostname")
        if hn_el is not None:
            hostname = hn_el.get("name")

        dtype = _guess_type(ip, mac, hostname, gateway_ips)
        nodes.append({"ip": ip, "mac": mac, "hostname": hostname, "device_type": dtype})
        print(f"    [{dtype:8s}]  {ip:16s}  {mac or 'no-mac':18s}  {hostname or ''}")

    return nodes


# ─── VAPT API client ──────────────────────────────────────────────────────────

def authenticate(base_url: str, username: str, password: str) -> str:
    url  = f"{base_url.rstrip('/')}/api/v1/auth/login"
    # API expects JSON body with email/password fields
    resp = requests.post(url, json={"email": username, "password": password}, timeout=10)
    if resp.status_code != 200:
        print(f"ERROR: Login failed ({resp.status_code}): {resp.text}")
        sys.exit(1)
    token = resp.json().get("access_token")
    if not token:
        print("ERROR: No access_token in response.")
        sys.exit(1)
    print(f"[+] Authenticated as {username}")
    return token


def submit(base_url: str, token: str, network_range: str, nodes: list[dict]) -> dict:
    url     = f"{base_url.rstrip('/')}/api/v1/network/import"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp    = requests.post(url, json={"network_range": network_range, "nodes": nodes},
                            headers=headers, timeout=30)
    if resp.status_code not in (200, 201):
        print(f"ERROR: Import failed ({resp.status_code}): {resp.text}")
        sys.exit(1)
    return resp.json()


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="VAPT Platform Host Scanner Agent"
    )
    p.add_argument("--url",      default="http://localhost:8000", help="Platform base URL")
    p.add_argument("--user",     required=True, help="Login email")
    p.add_argument("--password", required=True, help="Login password")
    p.add_argument("--range",    dest="network_range", help="CIDR to scan (e.g. 192.168.1.0/24)")
    p.add_argument("--dry-run",  action="store_true", help="Print results without submitting")
    args = p.parse_args()

    # Determine scan range
    if args.network_range:
        network_range = args.network_range
        print(f"[*] Using provided range: {network_range}")
    else:
        network_range = auto_detect_subnet()
        print(f"[*] Auto-detected subnet: {network_range}")

    nodes = scan_network(network_range)
    print(f"\n[*] {len(nodes)} host(s) found on {network_range}")

    if args.dry_run:
        print("\n[dry-run] Not submitting. Results:")
        print(json.dumps(nodes, indent=2))
        return

    if not nodes:
        print("[!] No hosts found — nothing to submit.")
        return

    token  = authenticate(args.url, args.user, args.password)
    result = submit(args.url, token, network_range, nodes)
    print(f"[+] Imported {result['nodes_imported']} node(s) | scan_id: {result['scan_id']}")
    print("[+] Refresh the Network page in the VAPT platform to see results.")


if __name__ == "__main__":
    main()
