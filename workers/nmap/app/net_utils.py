"""
net_utils.py — Cross-platform network interface helpers for the nmap worker.

Supports both Linux (using /proc/net/dev + ioctl) and Windows (using ipconfig).
"""

import platform
import re
import socket
import struct
import subprocess
from typing import Optional

_IS_WINDOWS = platform.system() == "Windows"


# ─── Shared helpers ───────────────────────────────────────────────────────────

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


def _classify(ip: str) -> dict:
    """Return is_docker and is_lan flags for an IP."""
    is_docker = _is_docker_ip(ip)
    is_lan = (
        ip.startswith("192.168.") or
        ip.startswith("10.") or
        bool(re.match(r"172\.(1[6-9]|2[0-9]|3[01])\.", ip))
    ) and not is_docker
    return {"is_docker": is_docker, "is_lan": is_lan}


# ─── Windows implementation ───────────────────────────────────────────────────

def _get_interfaces_windows() -> list[dict]:
    """Parse `ipconfig /all` to enumerate IPv4 interfaces on Windows."""
    results = []
    try:
        raw = subprocess.check_output(
            "ipconfig /all", shell=True, text=True,
            errors="replace", timeout=10
        )
        # Split into adapter blocks
        blocks = re.split(r"\r?\n\r?\n", raw)
        for block in blocks:
            ip_match = re.search(
                r"IPv4 Address[^:]*:\s*([\d.]+)", block, re.IGNORECASE
            )
            mask_match = re.search(
                r"Subnet Mask[^:]*:\s*([\d.]+)", block, re.IGNORECASE
            )
            name_match = re.match(r"([^\r\n]+):", block)
            if not ip_match or not mask_match:
                continue
            ip = ip_match.group(1).strip().rstrip("(Preferred)").strip()
            mask = mask_match.group(1).strip()
            if not re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
                continue
            prefix = _prefix_from_mask(mask)
            network = _network_address(ip, prefix)
            iface = name_match.group(1).strip() if name_match else "unknown"
            flags = _classify(ip)
            results.append({
                "interface": iface,
                "ip": ip,
                "prefix": prefix,
                "network_range": f"{network}/{prefix}",
                "family": "ipv4",
                **flags,
            })
    except Exception:
        pass
    return results


def _read_gateway_windows() -> Optional[str]:
    """Read the default gateway from `ipconfig` on Windows."""
    try:
        raw = subprocess.check_output(
            "ipconfig", shell=True, text=True, errors="replace", timeout=10
        )
        match = re.search(
            r"Default Gateway[^:]*:\s*([\d.]+)", raw, re.IGNORECASE
        )
        if match:
            gw = match.group(1).strip()
            if gw and gw != "0.0.0.0":
                return gw
    except Exception:
        pass
    return None


# ─── Linux implementation ─────────────────────────────────────────────────────

def _ioctl_addr(iface: str, request: int) -> Optional[str]:
    """Return dotted-decimal IPv4 result of an ioctl request (Linux only)."""
    try:
        from fcntl import ioctl  # noqa: PLC0415
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        packed = struct.pack("256s", iface[:15].encode())
        raw = ioctl(s.fileno(), request, packed)[20:24]
        s.close()
        return socket.inet_ntoa(raw)
    except Exception:
        return None


def _list_interfaces_linux() -> list[str]:
    """Return interface names from /proc/net/dev (excludes loopback)."""
    try:
        with open("/proc/net/dev") as f:
            lines = f.readlines()[2:]
        return [
            line.split(":")[0].strip()
            for line in lines
            if ":" in line and line.split(":")[0].strip() != "lo"
        ]
    except FileNotFoundError:
        return []


def _get_interfaces_linux() -> list[dict]:
    """Enumerate IPv4 interfaces on Linux using ioctl."""
    _SIOCGIFADDR = 0x8915
    _SIOCGIFNETMASK = 0x891B
    results = []
    for iface in _list_interfaces_linux():
        if any(iface.startswith(p) for p in ("docker", "br-", "veth", "virbr")):
            continue
        ip = _ioctl_addr(iface, _SIOCGIFADDR)
        mask = _ioctl_addr(iface, _SIOCGIFNETMASK)
        if not ip or not mask or ip.startswith("0.") or ip == "0.0.0.0":
            continue
        prefix = _prefix_from_mask(mask)
        network = _network_address(ip, prefix)
        flags = _classify(ip)
        results.append({
            "interface": iface,
            "ip": ip,
            "prefix": prefix,
            "network_range": f"{network}/{prefix}",
            "family": "ipv4",
            **flags,
        })
    return results


def _read_gateway_linux() -> Optional[str]:
    """Read default gateway from /proc/net/route (Linux only)."""
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                parts = line.strip().split()
                if len(parts) < 3:
                    continue
                if parts[1] == "00000000":  # default route
                    gw_bytes = bytes.fromhex(parts[2])[::-1]
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
    Works on both Windows and Linux.
    """
    if _IS_WINDOWS:
        return _get_interfaces_windows()
    return _get_interfaces_linux()


def _read_gateway() -> Optional[str]:
    """Read default gateway — cross-platform."""
    if _IS_WINDOWS:
        return _read_gateway_windows()
    return _read_gateway_linux()


def get_local_subnet() -> Optional[str]:
    """
    Return the CIDR subnet of the first active non-Docker LAN interface.
    Falls back to any non-loopback interface if no LAN interface is found.
    """
    ifaces = get_interfaces()
    for iface in ifaces:
        if iface["is_lan"]:
            return iface["network_range"]
    for iface in ifaces:
        if not iface["is_docker"]:
            return iface["network_range"]
    if ifaces:
        return ifaces[0]["network_range"]
    return None


def get_gateway_ips() -> set[str]:
    """Return the set of default gateway IPs (cross-platform)."""
    gateways: set[str] = set()
    gw = _read_gateway()
    if gw:
        gateways.add(gw)
    for iface in get_interfaces():
        base = iface["network_range"].rsplit(".", 1)[0]
        gateways.add(f"{base}.1")
        gateways.add(f"{base}.254")
    return gateways
