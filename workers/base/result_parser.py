"""
Common result parser for standardizing security tool outputs.

All tool workers should use this parser to convert their output to a
standardized format for consistent storage and reporting.
"""

from typing import Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass, asdict
import hashlib


class Severity(Enum):
    """Standardized severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    UNKNOWN = "unknown"


class VulnerabilityStatus(Enum):
    """Vulnerability status"""
    OPEN = "open"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    FIXED = "fixed"
    ACCEPTED = "accepted"


@dataclass
class Vulnerability:
    """Standardized vulnerability data structure"""
    vulnerability_id: str  # Unique identifier (generated or CVE ID)
    title: str
    description: str
    severity: str  # critical, high, medium, low, info
    cvss_score: Optional[float] = None
    cvss_vector: Optional[str] = None
    cve_id: Optional[str] = None
    cwe_id: Optional[str] = None
    
    # Location information
    host: Optional[str] = None
    port: Optional[int] = None
    protocol: Optional[str] = None
    service: Optional[str] = None
    url: Optional[str] = None
    path: Optional[str] = None
    
    # Additional details
    evidence: Optional[str] = None
    remediation: Optional[str] = None
    references: Optional[List[str]] = None
    
    # Tool information
    tool: Optional[str] = None
    tool_version: Optional[str] = None
    
    # Risk scoring
    exploitability: Optional[str] = None  # easy, medium, hard
    impact: Optional[str] = None  # high, medium, low
    
    # Status
    status: str = VulnerabilityStatus.OPEN.value
    confidence: Optional[str] = None  # certain, firm, tentative
    
    # Metadata
    discovered_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class ScanTarget:
    """Standardized scan target information"""
    target: str
    target_type: str  # ip, domain, url, container, cloud_account
    ip_address: Optional[str] = None
    hostname: Optional[str] = None
    os: Optional[str] = None
    os_version: Optional[str] = None
    open_ports: Optional[List[int]] = None
    services: Optional[Dict[int, str]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class ResultParser:
    """Base parser for standardizing tool outputs"""
    
    @staticmethod
    def generate_vuln_id(tool: str, target: str, title: str, location: str = "") -> str:
        """
        Generate unique vulnerability ID
        
        Args:
            tool: Tool name
            target: Target identifier
            title: Vulnerability title
            location: Location (host, port, url, etc.)
        
        Returns:
            Unique hash-based ID
        """
        data = f"{tool}:{target}:{title}:{location}"
        return hashlib.md5(data.encode()).hexdigest()[:16]
    
    @staticmethod
    def normalize_severity(severity: str) -> str:
        """
        Normalize severity to standard levels
        
        Args:
            severity: Raw severity string from tool
        
        Returns:
            Normalized severity (critical, high, medium, low, info)
        """
        severity = severity.lower().strip()
        
        severity_map = {
            'critical': Severity.CRITICAL.value,
            'high': Severity.HIGH.value,
            'medium': Severity.MEDIUM.value,
            'moderate': Severity.MEDIUM.value,
            'low': Severity.LOW.value,
            'informational': Severity.INFO.value,
            'info': Severity.INFO.value,
            'note': Severity.INFO.value,
        }
        
        return severity_map.get(severity, Severity.UNKNOWN.value)
    
    @staticmethod
    def cvss_to_severity(cvss_score: float) -> str:
        """
        Convert CVSS score to severity level
        
        Args:
            cvss_score: CVSS score (0.0-10.0)
        
        Returns:
            Severity level
        """
        if cvss_score >= 9.0:
            return Severity.CRITICAL.value
        elif cvss_score >= 7.0:
            return Severity.HIGH.value
        elif cvss_score >= 4.0:
            return Severity.MEDIUM.value
        elif cvss_score > 0.0:
            return Severity.LOW.value
        else:
            return Severity.INFO.value
    
    @staticmethod
    def extract_cve_ids(text: str) -> List[str]:
        """
        Extract CVE IDs from text
        
        Args:
            text: Text containing potential CVE IDs
        
        Returns:
            List of CVE IDs found
        """
        import re
        pattern = r'CVE-\d{4}-\d{4,7}'
        return re.findall(pattern, text, re.IGNORECASE)
    
    @staticmethod
    def extract_cwe_ids(text: str) -> List[str]:
        """
        Extract CWE IDs from text
        
        Args:
            text: Text containing potential CWE IDs
        
        Returns:
            List of CWE IDs found
        """
        import re
        pattern = r'CWE-\d+'
        return re.findall(pattern, text, re.IGNORECASE)


class NmapResultParser(ResultParser):
    """Parser for Nmap scan results"""
    
    @staticmethod
    def parse(nmap_data: List[Dict], target: str) -> Dict[str, Any]:
        """
        Parse Nmap XML output to standardized format
        
        Args:
            nmap_data: Parsed Nmap data (list of hosts)
            target: Original scan target
        
        Returns:
            Standardized result with targets and vulnerabilities
        """
        targets = []
        vulnerabilities = []
        
        for host_data in nmap_data:
            # Parse target information
            scan_target = ScanTarget(
                target=target,
                target_type='ip' if host_data.get('host') else 'domain',
                ip_address=host_data.get('host'),
                hostname=host_data.get('hostname'),
                os=host_data.get('os'),
                open_ports=[p['port'] for p in host_data.get('open_ports', [])],
                services={p['port']: p.get('service', 'unknown') for p in host_data.get('open_ports', [])}
            )
            targets.append(scan_target.to_dict())
            
            # Create vulnerabilities for open ports (informational)
            for port_info in host_data.get('open_ports', []):
                vuln = Vulnerability(
                    vulnerability_id=ResultParser.generate_vuln_id(
                        'nmap', host_data.get('host', target), 
                        f"Open Port {port_info['port']}", 
                        str(port_info['port'])
                    ),
                    title=f"Open Port: {port_info['port']}/{port_info.get('protocol', 'tcp')}",
                    description=f"Port {port_info['port']} is open running {port_info.get('service', 'unknown')} service",
                    severity=Severity.INFO.value,
                    host=host_data.get('host'),
                    port=port_info['port'],
                    protocol=port_info.get('protocol', 'tcp'),
                    service=port_info.get('service'),
                    tool='nmap',
                    confidence='certain',
                    metadata=port_info
                )
                vulnerabilities.append(vuln.to_dict())
        
        return {
            'targets': targets,
            'vulnerabilities': vulnerabilities,
            'summary': {
                'total_hosts': len(targets),
                'total_findings': len(vulnerabilities),
                'total_open_ports': sum(len(t.get('open_ports', [])) for t in targets)
            }
        }


class ZAPResultParser(ResultParser):
    """Parser for OWASP ZAP scan results"""
    
    @staticmethod
    def parse(zap_data: Dict, target: str) -> Dict[str, Any]:
        """
        Parse ZAP JSON output to standardized format
        
        Args:
            zap_data: ZAP scan results
            target: Original scan target
        
        Returns:
            Standardized result
        """
        vulnerabilities = []
        
        for alert in zap_data.get('alerts', []):
            # Extract CVE/CWE
            cve_ids = ResultParser.extract_cve_ids(alert.get('desc', '') + alert.get('solution', ''))
            cwe_ids = ResultParser.extract_cwe_ids(alert.get('desc', ''))
            
            vuln = Vulnerability(
                vulnerability_id=ResultParser.generate_vuln_id(
                    'zap', target, alert['name'], alert.get('url', '')
                ),
                title=alert['name'],
                description=alert.get('desc', ''),
                severity=ResultParser.normalize_severity(alert.get('risk', 'unknown')),
                cve_id=cve_ids[0] if cve_ids else None,
                cwe_id=cwe_ids[0] if cwe_ids else None,
                url=alert.get('url'),
                evidence=alert.get('evidence'),
                remediation=alert.get('solution'),
                references=alert.get('reference', '').split('\n') if alert.get('reference') else None,
                tool='zap',
                confidence=alert.get('confidence', '').lower(),
                metadata={
                    'attack': alert.get('attack'),
                    'param': alert.get('param'),
                    'method': alert.get('method'),
                }
            )
            vulnerabilities.append(vuln.to_dict())
        
        return {
            'targets': [{'target': target, 'target_type': 'url'}],
            'vulnerabilities': vulnerabilities,
            'summary': {
                'total_findings': len(vulnerabilities),
                'critical': sum(1 for v in vulnerabilities if v['severity'] == 'critical'),
                'high': sum(1 for v in vulnerabilities if v['severity'] == 'high'),
                'medium': sum(1 for v in vulnerabilities if v['severity'] == 'medium'),
                'low': sum(1 for v in vulnerabilities if v['severity'] == 'low'),
            }
        }


class TrivyResultParser(ResultParser):
    """Parser for Trivy scan results"""
    
    @staticmethod
    def parse(trivy_data: Dict, target: str) -> Dict[str, Any]:
        """
        Parse Trivy JSON output to standardized format
        
        Args:
            trivy_data: Trivy scan results
            target: Original scan target (image name, path, etc.)
        
        Returns:
            Standardized result
        """
        vulnerabilities = []
        
        for result in trivy_data.get('Results', []):
            target_name = result.get('Target', target)
            
            for vuln in result.get('Vulnerabilities', []):
                vulnerability = Vulnerability(
                    vulnerability_id=vuln.get('VulnerabilityID', ''),
                    title=vuln.get('Title', vuln.get('VulnerabilityID', 'Unknown')),
                    description=vuln.get('Description', ''),
                    severity=ResultParser.normalize_severity(vuln.get('Severity', 'unknown')),
                    cvss_score=vuln.get('CVSS', {}).get('nvd', {}).get('V3Score'),
                    cvss_vector=vuln.get('CVSS', {}).get('nvd', {}).get('V3Vector'),
                    cve_id=vuln.get('VulnerabilityID') if vuln.get('VulnerabilityID', '').startswith('CVE') else None,
                    cwe_id=vuln.get('CweIDs', [None])[0] if vuln.get('CweIDs') else None,
                    remediation=f"Update {vuln.get('PkgName')} to version {vuln.get('FixedVersion', 'latest')}",
                    references=vuln.get('References', []),
                    tool='trivy',
                    confidence='certain',
                    metadata={
                        'package': vuln.get('PkgName'),
                        'installed_version': vuln.get('InstalledVersion'),
                        'fixed_version': vuln.get('FixedVersion'),
                        'layer': vuln.get('Layer'),
                    }
                )
                vulnerabilities.append(vulnerability.to_dict())
        
        return {
            'targets': [{'target': target, 'target_type': 'container'}],
            'vulnerabilities': vulnerabilities,
            'summary': {
                'total_findings': len(vulnerabilities),
                'critical': sum(1 for v in vulnerabilities if v['severity'] == 'critical'),
                'high': sum(1 for v in vulnerabilities if v['severity'] == 'high'),
                'medium': sum(1 for v in vulnerabilities if v['severity'] == 'medium'),
                'low': sum(1 for v in vulnerabilities if v['severity'] == 'low'),
            }
        }


class ProwlerResultParser(ResultParser):
    """Parser for Prowler cloud security results"""
    
    @staticmethod
    def parse(prowler_data: List[Dict], target: str) -> Dict[str, Any]:
        """
        Parse Prowler JSON output to standardized format
        
        Args:
            prowler_data: Prowler scan results (list of findings)
            target: Cloud account/subscription ID
        
        Returns:
            Standardized result
        """
        vulnerabilities = []
        
        for finding in prowler_data:
            severity = finding.get('Severity', 'unknown')
            if severity == 'critical':
                sev = Severity.CRITICAL.value
            elif severity in ['high', 'fail']:
                sev = Severity.HIGH.value
            else:
                sev = ResultParser.normalize_severity(severity)
            
            vuln = Vulnerability(
                vulnerability_id=ResultParser.generate_vuln_id(
                    'prowler', target, finding.get('CheckID', ''),
                    finding.get('ResourceId', '')
                ),
                title=finding.get('CheckTitle', 'Cloud Security Finding'),
                description=finding.get('Description', ''),
                severity=sev,
                remediation=finding.get('Remediation', ''),
                tool='prowler',
                confidence='certain',
                metadata={
                    'check_id': finding.get('CheckID'),
                    'service': finding.get('ServiceName'),
                    'resource_id': finding.get('ResourceId'),
                    'region': finding.get('Region'),
                    'account_id': finding.get('AccountId'),
                    'status': finding.get('Status'),
                    'compliance': finding.get('Compliance', []),
                }
            )
            vulnerabilities.append(vuln.to_dict())
        
        return {
            'targets': [{'target': target, 'target_type': 'cloud_account'}],
            'vulnerabilities': vulnerabilities,
            'summary': {
                'total_findings': len(vulnerabilities),
                'critical': sum(1 for v in vulnerabilities if v['severity'] == 'critical'),
                'high': sum(1 for v in vulnerabilities if v['severity'] == 'high'),
                'medium': sum(1 for v in vulnerabilities if v['severity'] == 'medium'),
                'low': sum(1 for v in vulnerabilities if v['severity'] == 'low'),
            }
        }


class MetasploitResultParser(ResultParser):
    """Parser for Metasploit exploitation results"""
    
    @staticmethod
    def parse(msf_data: Dict, target: str) -> Dict[str, Any]:
        """
        Parse Metasploit results to standardized format
        
        Args:
            msf_data: Metasploit results
            target: Target identifier
        
        Returns:
            Standardized result
        """
        vulnerabilities = []
        
        # Metasploit results vary by module, this is a generic parser
        for vuln_data in msf_data.get('vulnerabilities', []):
            vuln = Vulnerability(
                vulnerability_id=vuln_data.get('id', ResultParser.generate_vuln_id(
                    'metasploit', target, vuln_data.get('name', 'Unknown')
                )),
                title=vuln_data.get('name', 'Exploitation Result'),
                description=vuln_data.get('description', ''),
                severity=Severity.HIGH.value,  # Exploitable vulns are at least HIGH
                host=vuln_data.get('host'),
                port=vuln_data.get('port'),
                service=vuln_data.get('service'),
                evidence=vuln_data.get('output'),
                remediation=vuln_data.get('remediation'),
                tool='metasploit',
                exploitability='confirmed',  # If Metasploit exploited it
                confidence='certain',
                metadata={
                    'module': vuln_data.get('module'),
                    'exploit_result': vuln_data.get('result'),
                }
            )
            vulnerabilities.append(vuln.to_dict())
        
        return {
            'targets': [{'target': target, 'target_type': 'ip'}],
            'vulnerabilities': vulnerabilities,
            'summary': {
                'total_findings': len(vulnerabilities),
                'exploited': sum(1 for v in vulnerabilities if v.get('metadata', {}).get('exploit_result') == 'success'),
            }
        }
