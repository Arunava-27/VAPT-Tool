import logging
import time
import sys
import os
import re

# Add parent directories to path to import base classes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'base'))

from .config import celery_app
from .scanner import NmapScanner
from .parser import parse_nmap_xml
from .net_utils import get_local_subnet, get_gateway_ips, get_interfaces as _net_get_interfaces
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


def _guess_device_type(mac: str, hostname: str, gateway_ips: set = None) -> str:
    """Guess device type from IP (gateway check), MAC OUI prefix, and hostname."""
    # Gateway IPs are always routers
    if gateway_ips and mac is None:
        # If no MAC, it might be us or the gateway — skip
        pass

    if hostname:
        h = hostname.lower()
        if any(x in h for x in ["router", "gateway", "gw", "rt-", "rtr", "dlink", "tp-link", "linksys", "netgear", "asus", "mikrotik", "ubnt", "unifi", "edgerouter", "airmax"]):
            return "router"
        if any(x in h for x in ["switch", "sw-", "sw.", "cisco", "catalyst", "nexus"]):
            return "switch"
        if any(x in h for x in ["server", "srv", "nas", "storage", "synology", "qnap"]):
            return "server"
        if any(x in h for x in ["android", "iphone", "ipad", "pixel", "samsung-m", "oneplus", "xiaomi", "huawei", "oppo", "vivo", "realme"]):
            return "mobile"
        if any(x in h for x in ["printer", "print", "hp-", "epson", "canon-", "brother", "ricoh"]):
            return "printer"
        if any(x in h for x in ["camera", "cam-", "nvr", "dvr", "hikvision", "dahua", "ring", "nest-cam"]):
            return "iot"
    if mac:
        oui = mac[:8].upper()
        # Common router/AP vendors
        router_ouis = {
            "D8:07:B6", "50:C7:BF", "E4:8D:8C", "B0:BE:76", "A4:2B:B0",
            "F8:1A:67", "E0:28:6D", "00:50:56", "08:00:27", "A0:63:91",
            "10:C3:7B", "00:1D:AA", "00:26:B9", "C8:D7:19", "68:7F:74",
            "18:A6:F7", "BC:76:70", "D4:6E:0E", "30:B4:9E", "B0:4E:26",
        }
        if oui in router_ouis:
            return "router"
        mobile_prefixes = ["AC:BC", "DC:2B", "A4:C3", "04:D3", "02:00", "3A:93", "4A:15"]
        if any(mac.upper().startswith(p) for p in mobile_prefixes):
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
    import subprocess
    import xml.etree.ElementTree as ET
    import psycopg2
    import psycopg2.extras

    network_range = task_data.get("network_range")
    scan_id = task_data.get("scan_id")

    # Auto-detect subnet via pure-Python ioctl (no subprocess/iproute2 needed)
    if not network_range:
        network_range = get_local_subnet() or "192.168.1.0/24"
        logger.info(f"Auto-detected subnet: {network_range}")

    # Detect gateway IPs via /proc/net/route (pure kernel read)
    gateway_ips = get_gateway_ips()

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

        # Multi-probe discovery: ICMP echo + TCP SYN to common ports + TCP ACK
        # This finds WiFi/mobile devices that block ICMP pings.
        # --send-ip: use IP-level probes (required when not on same L2 subnet, e.g. Docker bridge)
        # -PE: ICMP echo  -PP: ICMP timestamp  -PM: ICMP netmask
        # -PS: TCP SYN    -PA: TCP ACK          -PU: UDP
        cmd = [
            "nmap", "-sn",
            "--send-ip",
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
        logger.info(f"Running nmap: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        logger.info(f"nmap returncode={result.returncode}, stdout_len={len(result.stdout)}, stderr={result.stderr[:500] if result.stderr else ''}")
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

                # Classify: gateway IPs → router regardless of MAC/hostname
                if ip in gateway_ips:
                    device_type = "router"
                else:
                    device_type = _guess_device_type(mac, hostname, gateway_ips)

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

        # ── Parse vuln scripts and build host_vulnerabilities entries ──────────
        vulnerabilities = []
        if xml_out and node_id:
            vroot = ET.fromstring(xml_out)
            for host_el in vroot.findall("host"):
                ports_el = host_el.find("ports")
                if not ports_el:
                    continue
                for port_el in ports_el.findall("port"):
                    state_el = port_el.find("state")
                    if state_el is None or state_el.get("state") != "open":
                        continue
                    portid = int(port_el.get("portid", 0))
                    proto = port_el.get("protocol", "tcp")
                    svc_el = port_el.find("service")
                    svc_name = svc_el.get("name", "") if svc_el is not None else ""
                    svc_product = svc_el.get("product", "") if svc_el is not None else ""
                    svc_version = svc_el.get("version", "") if svc_el is not None else ""

                    # Info-level finding for every open port/service
                    svc_desc = " ".join(filter(None, [svc_product, svc_version]))
                    vulnerabilities.append({
                        "vuln_id": f"service-{portid}-{proto}",
                        "title": f"Open Port: {svc_name or 'unknown'} on {portid}/{proto}",
                        "severity": "info",
                        "description": f"Port {portid}/{proto} is open{(': ' + svc_desc) if svc_desc else ''}",
                        "cve_id": None,
                        "cvss_score": None,
                        "port": portid,
                        "protocol": proto,
                        "service": svc_name,
                        "evidence": svc_desc or None,
                        "remediation": None,
                    })

                    # Parse nmap script output for CVEs and vulnerabilities
                    for script_el in port_el.findall("script"):
                        script_id = script_el.get("id", "")
                        script_output = script_el.get("output", "")
                        cve_ids = list(set(re.findall(r'CVE-\d{4}-\d+', script_output)))

                        if cve_ids:
                            for cve_id in cve_ids:
                                # Extract CVSS score if present in output
                                cvss_match = re.search(r'\b(\d+\.\d)\b', script_output)
                                cvss_score = float(cvss_match.group(1)) if cvss_match else None
                                if cvss_score is not None:
                                    if cvss_score >= 9.0:
                                        severity = "critical"
                                    elif cvss_score >= 7.0:
                                        severity = "high"
                                    elif cvss_score >= 4.0:
                                        severity = "medium"
                                    else:
                                        severity = "low"
                                else:
                                    severity = "high"
                                vulnerabilities.append({
                                    "vuln_id": f"{script_id}-{cve_id}-{portid}",
                                    "title": f"{cve_id} – {svc_name or 'unknown'} ({portid}/{proto})",
                                    "severity": severity,
                                    "description": f"Vulnerability detected by nmap script '{script_id}'",
                                    "cve_id": cve_id,
                                    "cvss_score": cvss_score,
                                    "port": portid,
                                    "protocol": proto,
                                    "service": svc_name,
                                    "evidence": script_output[:500] if script_output else None,
                                    "remediation": None,
                                })
                        elif script_output and any(kw in script_output for kw in ["VULNERABLE", "vulnerable", "exploit"]):
                            vulnerabilities.append({
                                "vuln_id": f"{script_id}-{portid}",
                                "title": f"Potential vulnerability: {script_id} on {portid}/{proto}",
                                "severity": "medium",
                                "description": f"nmap script '{script_id}' flagged a potential vulnerability",
                                "cve_id": None,
                                "cvss_score": None,
                                "port": portid,
                                "protocol": proto,
                                "service": svc_name,
                                "evidence": script_output[:500] if script_output else None,
                                "remediation": None,
                            })

        # ── Persist vulnerabilities and compute risk score ─────────────────────
        if vulnerabilities and node_id:
            # Replace all vulns for this node with fresh scan results
            cur.execute("DELETE FROM host_vulnerabilities WHERE node_id=%s", (node_id,))
            for vuln in vulnerabilities:
                cur.execute("""
                    INSERT INTO host_vulnerabilities
                        (node_id, scan_id, vuln_id, title, severity, description,
                         cve_id, cvss_score, port, protocol, service, evidence, remediation)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    node_id, scan_id,
                    vuln["vuln_id"], vuln["title"], vuln["severity"], vuln.get("description"),
                    vuln.get("cve_id"), vuln.get("cvss_score"),
                    vuln.get("port"), vuln.get("protocol"), vuln.get("service"),
                    vuln.get("evidence"), vuln.get("remediation"),
                ))

            # Compute risk_score = critical×40 + high×15 + medium×5 + low×1
            sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for v in vulnerabilities:
                s = v["severity"]
                if s in sev_counts:
                    sev_counts[s] += 1
            risk_score = min(100,
                sev_counts["critical"] * 40 + sev_counts["high"] * 15 +
                sev_counts["medium"] * 5 + sev_counts["low"] * 1
            )
            if node_id:
                cur.execute("UPDATE network_nodes SET risk_score=%s WHERE id=%s", (risk_score, node_id))

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
    Return network interfaces visible to the nmap worker.
    Delegates to net_utils which uses pure-Python ioctl + /proc/net/route —
    no subprocess, no iproute2 binary required.
    """
    from .net_utils import get_interfaces as _ifaces, _read_gateway

    interfaces = _ifaces()
    gateway_ip = _read_gateway()

    return {
        "interfaces": interfaces,
        "gateway_ip": gateway_ip,
    }