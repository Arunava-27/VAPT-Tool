"""
net_utils.py — Pure-Python network interface helpers for the nmap worker.

Uses kernel interfaces (/proc/net/dev, ioctl SIOCGIFADDR/SIOCGIFNETMASK)
instead of subprocess calls to `ip` or `ifconfig`, so it works even when
iproute2 is not installed and never fails due to a missing binary.
"""

import re
import socket
import struct
from fcntl import ioctl
from typing import Optional

# ioctl request codes (Linux/arm64 & x86_64 — same values)
_SIOCGIFADDR    = 0x8915   # get interface IPv4 address
_SIOCGIFNETMASK = 0x891B   # get interface netmask


def _ioctl_addr(iface: str, request: int) -> Optional[str]:
    """Return dotted-decimal IPv4 result of an ioctl request, or None."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        packed = struct.pack("256s", iface[:15].encode())
        raw = ioctl(s.fileno(), request, packed)[20:24]
        s.close()
        return socket.inet_ntoa(raw)
    except OSError:
        return None


def _prefix_from_mask(mask: str) -> int:
    """Convert dotted-decimal netmask to prefix length (e.g. '255.255.255.0' → 24)."""
    return bin(struct.unpack(">I", socket.inet_aton(mask))[0]).count("1")


def _network_address(ip: str, prefix: int) -> str:
    """Return network address string for ip/prefix (e.g. '192.168.1.55', 24 → '192.168.1.0')."""
    ip_int = struct.unpack(">I", socket.inet_aton(ip))[0]
    mask_int = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    net_int = ip_int & mask_int
    return socket.inet_ntoa(struct.pack(">I", net_int))


def _is_docker_ip(ip: str) -> bool:
    """True if ip falls in the Docker bridge range 172.16–31.x.x."""
    return bool(re.match(r"172\.(1[6-9]|2[0-9]|3[01])\.", ip))


def _list_interfaces() -> list[str]:
    """Return interface names from /proc/net/dev (excludes loopback)."""
    try:
        with open("/proc/net/dev") as f:
            lines = f.readlines()[2:]  # first two lines are headers
        return [
            line.split(":")[0].strip()
            for line in lines
            if ":" in line and line.split(":")[0].strip() != "lo"
        ]
    except FileNotFoundError:
        return []


def _read_gateway() -> Optional[str]:
    """
    Read the default gateway IP from /proc/net/route (pure kernel, no subprocess).
    Returns the first default-route gateway as a dotted-decimal string, or None.
    """
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:   # skip header
                parts = line.strip().split()
                if len(parts) < 3:
                    continue
                destination = parts[1]
                gateway_hex = parts[2]
                if destination == "00000000":  # 0.0.0.0 = default route
                    # Gateway is stored in little-endian hex
                    gw_bytes = bytes.fromhex(gateway_hex)[::-1]
                    gw_ip = socket.inet_ntoa(gw_bytes)
                    if gw_ip != "0.0.0.0":
                        return gw_ip
    except Exception:
        pass
    return None


# ─── Public API ───────────────────────────────────────────────────────────────

def get_interfaces() -> list[dict]:
    """
    Return a list of dicts for every non-loopback IPv4 interface:
      {interface, ip, prefix, network_range, family, is_docker, is_lan}

    Uses pure Python ioctl — no subprocess / no iproute2 required.
    """
    results = []
    for iface in _list_interfaces():
        # Skip virtual/Docker bridge interfaces
        if any(iface.startswith(p) for p in ("docker", "br-", "veth", "virbr")):
            continue

        ip = _ioctl_addr(iface, _SIOCGIFADDR)
        mask = _ioctl_addr(iface, _SIOCGIFNETMASK)
        if not ip or not mask or ip.startswith("0.") or ip == "0.0.0.0":
            continue

        prefix = _prefix_from_mask(mask)
        network = _network_address(ip, prefix)
        is_docker = _is_docker_ip(ip)
        is_lan = (
            ip.startswith("192.168.") or
            ip.startswith("10.") or
            bool(re.match(r"172\.(1[6-9]|2[0-9]|3[01])\.", ip))
        ) and not is_docker

        results.append({
            "interface": iface,
            "ip": ip,
            "prefix": prefix,
            "network_range": f"{network}/{prefix}",
            "family": "ipv4",
            "is_docker": is_docker,
            "is_lan": is_lan,
        })

    return results


def get_local_subnet() -> Optional[str]:
    """
    Return the CIDR subnet of the first active non-Docker LAN interface.
    Falls back to any non-loopback interface if no LAN interface is found.
    Returns None only if no usable interface exists at all.
    """
    ifaces = get_interfaces()

    # Prefer genuine LAN interfaces
    for iface in ifaces:
        if iface["is_lan"]:
            return iface["network_range"]

    # Fall back to any non-Docker interface
    for iface in ifaces:
        if not iface["is_docker"]:
            return iface["network_range"]

    # Last resort: Docker bridge (still better than nothing)
    if ifaces:
        return ifaces[0]["network_range"]

    return None


def get_gateway_ips() -> set[str]:
    """
    Return the set of default gateway IPs.
    Reads /proc/net/route (pure kernel) with fallback guesses.
    """
    gateways: set[str] = set()

    gw = _read_gateway()
    if gw:
        gateways.add(gw)

    # Also guess common gateway addresses from discovered subnets
    for iface in get_interfaces():
        base = iface["network_range"].rsplit(".", 1)[0]
        gateways.add(f"{base}.1")
        gateways.add(f"{base}.254")

    return gateways
