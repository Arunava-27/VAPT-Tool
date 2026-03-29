import logging
import time
import sys
import os

# Add parent directories to path to import base classes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'base'))

from .config import celery_app
from .scanner import NmapScanner
from .parser import parse_nmap_xml
from base_task import BaseTask, ErrorCategory, TaskError
from result_parser import NmapResultParser

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create base task instance
base_task = BaseTask()


@celery_app.task(name="nmap.scan", bind=True)
def nmap_scan(self, task_data):
    """
    Enhanced Nmap scan task with retry logic and standardized output
    
    Args:
        task_data: Dictionary containing:
            - target: Target to scan (required)
            - profile: Scan profile (quick, comprehensive, stealth, custom)
            - ports: Port specification (optional)
            - options: Additional scan options (optional)
    
    Returns:
        Standardized result dictionary
    """
    target = task_data.get("target")
    profile = task_data.get("profile", "quick")
    ports = task_data.get("ports")
    options = task_data.get("options", {})
    scan_id = task_data.get("scan_id")
    
    start_time = time.time()
    
    try:
        # Validate input
        if not target:
            raise TaskError("Target is required", ErrorCategory.INVALID_INPUT)
        
        base_task.log_start(self.request.id, target, "nmap")
        if scan_id:
            base_task.update_scan_status(scan_id, "running")
        base_task.log_progress(self.request.id, f"Using profile: {profile}", "nmap")
        
        # Step 1: Run scan with retry logic
        def run_scan():
            return NmapScanner.run_scan(target, profile, ports, options, timeout=options.get('timeout', 120))
        
        xml_output = base_task.with_retry(
            run_scan,
            max_retries=options.get('max_retries', 2),
            task_id=self.request.id,
            tool="nmap"
        )
        
        base_task.log_progress(self.request.id, "Scan completed, parsing results", "nmap")
        
        # Step 2: Parse XML output
        parsed_hosts = parse_nmap_xml(xml_output)
        
        # Step 3: Convert to standardized format
        standardized_result = NmapResultParser.parse(parsed_hosts, target)
        
        base_task.log_progress(self.request.id, 
                              f"Found {standardized_result['summary']['total_open_ports']} open ports", 
                              "nmap")
        
        # Step 4: Create final result
        duration = time.time() - start_time
        result = base_task.create_result(
            status='completed',
            task_id=self.request.id,
            tool='nmap',
            target=target,
            result_data=standardized_result,
            error=None,
            metadata={
                'profile': profile,
                'ports': ports,
                'duration': duration,
                'scan_options': options
            }
        )
        
        # Validate result structure
        if not base_task.validate_result(result):
            raise TaskError("Result validation failed", ErrorCategory.TOOL_ERROR)
        
        if scan_id:
            base_task.update_scan_status(scan_id, "completed", standardized_result.get('summary', {}))
        base_task.log_success(self.request.id, duration, "nmap")
        return result
    
    except TaskError as e:
        # Categorized error
        base_task.log_error(self.request.id, e, e.category, "nmap")
        if scan_id:
            base_task.update_scan_status(scan_id, "failed", error=str(e))
        
        return base_task.create_result(
            status='failed',
            task_id=self.request.id,
            tool='nmap',
            target=target,
            result_data=None,
            error=str(e),
            metadata={
                'error_category': e.category.value,
                'duration': time.time() - start_time
            }
        )
    
    except Exception as e:
        # Uncategorized error
        category = base_task.categorize_error(e)
        base_task.log_error(self.request.id, e, category, "nmap")
        if scan_id:
            base_task.update_scan_status(scan_id, "failed", error=str(e))
        
        return base_task.create_result(
            status='failed',
            task_id=self.request.id,
            tool='nmap',
            target=target,
            result_data=None,
            error=str(e),
            metadata={
                'error_category': category.value,
                'duration': time.time() - start_time
            }
        )


def _guess_device_type(mac: str, hostname: str) -> str:
    """Guess device type from MAC OUI prefix and hostname."""
    if hostname:
        h = hostname.lower()
        if any(x in h for x in ["router", "gateway", "gw", "rt-", "rtr"]):
            return "router"
        if any(x in h for x in ["switch", "sw-", "sw."]):
            return "switch"
        if any(x in h for x in ["server", "srv", "nas", "storage"]):
            return "server"
        if any(x in h for x in ["android", "iphone", "ipad", "pixel", "samsung-m", "oneplus"]):
            return "mobile"
        if any(x in h for x in ["printer", "print", "hp-", "epson", "canon-"]):
            return "printer"
        if any(x in h for x in ["camera", "cam-", "nvr", "dvr"]):
            return "iot"
    if mac:
        oui = mac[:8].upper()
        if oui in ["D8:07:B6", "50:C7:BF", "E4:8D:8C", "B0:BE:76", "A4:2B:B0", "00:50:56", "08:00:27"]:
            return "router"
        if oui[:5] in ["AC:BC", "DC:2B", "A4:C3", "04:D3"]:
            return "mobile"
    return "pc"


@celery_app.task(name="nmap.network_discover", bind=True)
def network_discover(self, task_data):
    """
    Discover all live hosts on a network range using ARP + ping sweep.
    task_data keys:
      - network_range: CIDR like "192.168.1.0/24" (auto-detected if not given)
      - scan_id: UUID to update in DB
    """
    import socket
    import subprocess
    import xml.etree.ElementTree as ET
    import psycopg2
    import psycopg2.extras
    import re

    network_range = task_data.get("network_range")
    scan_id = task_data.get("scan_id")

    # Auto-detect network range if not provided
    if not network_range:
        try:
            result = subprocess.run(
                ["ip", "route", "get", "1.1.1.1"],
                capture_output=True, text=True, timeout=5
            )
            match = re.search(r'src\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
            if match:
                src_ip = match.group(1)
                parts = src_ip.split('.')
                network_range = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        except Exception:
            network_range = "192.168.1.0/24"

    conn = None
    cur = None
    try:
        db_url = os.getenv("DATABASE_URL", "postgresql://vapt_user:changeme123@localhost:5432/vapt_platform")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        if scan_id:
            cur.execute(
                "UPDATE network_scans SET status='running', network_range=%s WHERE id=%s",
                (network_range, scan_id)
            )
            conn.commit()

        cmd = ["nmap", "-sn", "--send-ip", "-T4", "--host-timeout", "10s", "-oX", "-", network_range]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        xml_out = result.stdout

        nodes = []
        if xml_out:
            root = ET.fromstring(xml_out)
            for host in root.findall("host"):
                state = host.find("status")
                if state is None or state.get("state") != "up":
                    continue

                ip = None
                mac = None
                for addr in host.findall("address"):
                    if addr.get("addrtype") == "ipv4":
                        ip = addr.get("addr")
                    elif addr.get("addrtype") == "mac":
                        mac = addr.get("addr")

                if not ip:
                    continue

                hostname_el = host.find(".//hostname")
                hostname = hostname_el.get("name") if hostname_el is not None else None
                device_type = _guess_device_type(mac, hostname)

                cur.execute("""
                    INSERT INTO network_nodes
                        (ip_address, mac_address, hostname, device_type, network_range, status, last_seen_at)
                    VALUES (%s, %s, %s, %s, %s, 'active', NOW())
                    ON CONFLICT (ip_address) DO UPDATE SET
                        mac_address = COALESCE(EXCLUDED.mac_address, network_nodes.mac_address),
                        hostname    = COALESCE(EXCLUDED.hostname, network_nodes.hostname),
                        device_type = EXCLUDED.device_type,
                        status      = 'active',
                        last_seen_at = NOW()
                    RETURNING id
                """, (ip, mac, hostname, device_type, network_range))
                node_id = cur.fetchone()[0]
                nodes.append({
                    "id": str(node_id),
                    "ip": ip,
                    "mac": mac,
                    "hostname": hostname,
                    "device_type": device_type,
                })

            conn.commit()

        nodes_found = len(nodes)
        if scan_id:
            cur.execute("""
                UPDATE network_scans
                SET status='completed', nodes_found=%s, completed_at=NOW(), result=%s
                WHERE id=%s
            """, (nodes_found, psycopg2.extras.Json({"nodes": nodes, "network_range": network_range}), scan_id))
            conn.commit()

        cur.close()
        conn.close()
        return {"status": "completed", "nodes_found": nodes_found, "network_range": network_range, "nodes": nodes}

    except Exception as e:
        logger.error(f"network_discover failed: {e}")
        if scan_id and conn and cur:
            try:
                cur.execute(
                    "UPDATE network_scans SET status='failed', error=%s WHERE id=%s",
                    (str(e), scan_id)
                )
                conn.commit()
            except Exception:
                pass
        if cur:
            cur.close()
        if conn:
            conn.close()
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="nmap.node_scan", bind=True)
def node_scan(self, task_data):
    """
    Full port + service + OS scan on a specific node.
    Updates network_nodes table with results.
    task_data keys:
      - target: IP address to scan
      - scan_id: UUID to update in DB
      - node_id: UUID of network_node record
      - profile: quick/comprehensive/vuln (default: comprehensive)
    """
    import subprocess
    import xml.etree.ElementTree as ET
    import psycopg2
    import psycopg2.extras

    target = task_data.get("target")
    scan_id = task_data.get("scan_id")
    node_id = task_data.get("node_id")
    profile = task_data.get("profile", "comprehensive")

    if not target:
        return {"status": "failed", "error": "target required"}

    conn = None
    cur = None
    try:
        db_url = os.getenv("DATABASE_URL", "postgresql://vapt_user:changeme123@localhost:5432/vapt_platform")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        if scan_id:
            cur.execute("UPDATE network_scans SET status='running' WHERE id=%s", (scan_id,))
            conn.commit()

        if profile == "quick":
            cmd = ["nmap", "-F", "-T4", "-sV", "--host-timeout", "60s", "-oX", "-", target]
        elif profile == "vuln":
            cmd = ["nmap", "-sV", "-T4", "--script", "vuln", "-p-", "--host-timeout", "600s", "-oX", "-", target]
        else:  # comprehensive
            cmd = ["nmap", "-A", "-T4", "-p-", "--host-timeout", "300s", "-oX", "-", target]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=700)
        xml_out = result.stdout

        open_ports = []
        services = []
        os_family = None
        os_version = None

        if xml_out:
            root = ET.fromstring(xml_out)
            for host in root.findall("host"):
                ports_el = host.find("ports")
                if ports_el:
                    for port in ports_el.findall("port"):
                        state = port.find("state")
                        if state is None or state.get("state") != "open":
                            continue
                        portid = int(port.get("portid", 0))
                        proto = port.get("protocol", "tcp")
                        svc = port.find("service")
                        svc_name = svc.get("name", "") if svc is not None else ""
                        svc_product = svc.get("product", "") if svc is not None else ""
                        svc_version = svc.get("version", "") if svc is not None else ""
                        open_ports.append(portid)
                        services.append({
                            "port": portid,
                            "protocol": proto,
                            "service": svc_name,
                            "product": svc_product,
                            "version": svc_version,
                        })
                os_el = host.find("os")
                if os_el:
                    match_el = os_el.find(".//osmatch")
                    if match_el is not None:
                        os_version = match_el.get("name")
                        osclass = match_el.find("osclass")
                        if osclass is not None:
                            os_family = osclass.get("osfamily")

        if node_id:
            cur.execute("""
                UPDATE network_nodes SET
                    open_ports=%s, services=%s, os_family=%s, os_version=%s,
                    last_seen_at=NOW(), last_scan_id=%s
                WHERE id=%s
            """, (
                psycopg2.extras.Json(open_ports),
                psycopg2.extras.Json(services),
                os_family, os_version,
                scan_id, node_id,
            ))

        if scan_id:
            cur.execute("""
                UPDATE network_scans SET status='completed', completed_at=NOW(), result=%s
                WHERE id=%s
            """, (
                psycopg2.extras.Json({
                    "open_ports": open_ports,
                    "services": services,
                    "os_family": os_family,
                    "os_version": os_version,
                }),
                scan_id,
            ))

        conn.commit()
        cur.close()
        conn.close()
        return {"status": "completed", "target": target, "open_ports": open_ports, "services": services}

    except Exception as e:
        logger.error(f"node_scan failed: {e}")
        if scan_id and conn and cur:
            try:
                cur.execute(
                    "UPDATE network_scans SET status='failed', error=%s WHERE id=%s",
                    (str(e), scan_id)
                )
                conn.commit()
            except Exception:
                pass
        if cur:
            cur.close()
        if conn:
            conn.close()
        return {"status": "failed", "error": str(e)}

@celery_app.task(name="nmap.get_interfaces")
def get_interfaces():
    """
    Return network interfaces as seen by the nmap worker (host network mode).
    Called by the API gateway to show the real LAN interfaces of the Docker host,
    not the Docker bridge interfaces visible inside the gateway container.
    """
    import subprocess
    import re

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
            if iface in ("lo",):
                continue
            family = parts[2]
            if family != "inet":
                continue
            cidr = parts[3]
            ip, prefix = cidr.split("/") if "/" in cidr else (cidr, "24")
            octets = ip.split(".")
            network_range = f"{octets[0]}.{octets[1]}.{octets[2]}.0/{prefix}"

            # Classify: private LAN or Docker bridge (172.16-31.x.x)
            is_docker = bool(re.match(r"172\.(1[6-9]|2[0-9]|3[01])\.", ip))
            is_lan = (
                ip.startswith("192.168.") or
                ip.startswith("10.") or
                bool(re.match(r"172\.(1[6-9]|2[0-9]|3[01])\.", ip))
            ) and not is_docker

            interfaces.append({
                "interface": iface,
                "ip": ip,
                "prefix": int(prefix),
                "network_range": network_range,
                "family": "ipv4",
                "is_docker": is_docker,
                "is_lan": is_lan,
            })
    except Exception as e:
        return {"interfaces": [], "error": str(e)}

    return {"interfaces": interfaces}