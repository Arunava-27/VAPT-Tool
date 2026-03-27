"""
Result aggregator - Collects and merges results from multiple workers
"""

from typing import Dict, List, Set, Tuple
from uuid import UUID
import logging
from collections import defaultdict

from ..models.scan_models import (
    ScanJob,
    ScanResult,
    VulnerabilityFinding,
    VulnerabilitySeverity,
    WorkerTask,
    ScanStatus
)
from ..core.config import settings

logger = logging.getLogger(__name__)


class ResultAggregator:
    """
    Aggregates scan results from multiple workers
    
    Features:
    - Deduplicates findings across tools
    - Merges related vulnerabilities
    - Calculates risk scores
    - Generates summary statistics
    """
    
    def __init__(self):
        """Initialize result aggregator"""
        self.severity_weights = {
            VulnerabilitySeverity.CRITICAL: 10.0,
            VulnerabilitySeverity.HIGH: 7.0,
            VulnerabilitySeverity.MEDIUM: 4.0,
            VulnerabilitySeverity.LOW: 2.0,
            VulnerabilitySeverity.INFO: 0.5
        }
    
    def aggregate_results(self, scan_job: ScanJob) -> ScanResult:
        """
        Aggregate results from all worker tasks
        
        Args:
            scan_job: Scan job with completed worker tasks
        
        Returns:
            Aggregated scan result
        """
        logger.info(f"Aggregating results for scan {scan_job.id}")
        
        # Collect all vulnerabilities from worker tasks
        all_vulnerabilities: List[VulnerabilityFinding] = []
        tools_used: Set[str] = set()
        
        for worker_task in scan_job.worker_tasks:
            if worker_task.status == ScanStatus.COMPLETED and worker_task.result:
                # Extract vulnerabilities from worker result
                task_vulnerabilities = self._extract_vulnerabilities(worker_task)
                all_vulnerabilities.extend(task_vulnerabilities)
                tools_used.add(worker_task.worker_type.value)
        
        logger.info(f"Collected {len(all_vulnerabilities)} vulnerabilities from {len(tools_used)} tools")
        
        # Deduplicate if enabled
        if settings.DEDUPLICATION_ENABLED:
            deduplicated = self._deduplicate_vulnerabilities(all_vulnerabilities)
            logger.info(f"Deduplicated to {len(deduplicated)} unique vulnerabilities")
            all_vulnerabilities = deduplicated
        
        # Calculate severity counts
        severity_counts = self._count_by_severity(all_vulnerabilities)
        
        # Calculate risk score
        risk_score = self._calculate_risk_score(all_vulnerabilities)
        risk_level = self._determine_risk_level(risk_score)
        
        # Create scan result
        scan_result = ScanResult(
            scan_id=scan_job.scan_id,
            scan_job_id=scan_job.id,
            status=scan_job.status,
            total_vulnerabilities=len(all_vulnerabilities),
            critical_count=severity_counts[VulnerabilitySeverity.CRITICAL],
            high_count=severity_counts[VulnerabilitySeverity.HIGH],
            medium_count=severity_counts[VulnerabilitySeverity.MEDIUM],
            low_count=severity_counts[VulnerabilitySeverity.LOW],
            info_count=severity_counts[VulnerabilitySeverity.INFO],
            vulnerabilities=all_vulnerabilities,
            scan_duration_seconds=self._calculate_duration(scan_job),
            targets_scanned=len(set(t.target.value for t in scan_job.worker_tasks)),
            tools_used=sorted(list(tools_used)),
            overall_risk_score=risk_score,
            risk_level=risk_level
        )
        
        # Update scan job with summary
        scan_job.vulnerabilities_found = len(all_vulnerabilities)
        scan_job.critical_count = severity_counts[VulnerabilitySeverity.CRITICAL]
        scan_job.high_count = severity_counts[VulnerabilitySeverity.HIGH]
        scan_job.medium_count = severity_counts[VulnerabilitySeverity.MEDIUM]
        scan_job.low_count = severity_counts[VulnerabilitySeverity.LOW]
        scan_job.info_count = severity_counts[VulnerabilitySeverity.INFO]
        
        logger.info(
            f"Aggregation complete: {scan_result.total_vulnerabilities} vulnerabilities "
            f"(C:{scan_result.critical_count}, H:{scan_result.high_count}, "
            f"M:{scan_result.medium_count}, L:{scan_result.low_count}, I:{scan_result.info_count})"
        )
        
        return scan_result
    
    def _extract_vulnerabilities(self, worker_task: WorkerTask) -> List[VulnerabilityFinding]:
        """
        Extract vulnerability findings from worker task result
        
        Args:
            worker_task: Completed worker task
        
        Returns:
            List of vulnerability findings
        """
        if not worker_task.result or 'vulnerabilities' not in worker_task.result:
            return []
        
        vulnerabilities = []
        
        for vuln_data in worker_task.result['vulnerabilities']:
            # Convert dict to VulnerabilityFinding
            try:
                vulnerability = VulnerabilityFinding(
                    vulnerability_id=vuln_data.get('vulnerability_id', 'UNKNOWN'),
                    title=vuln_data.get('title', 'Unknown Vulnerability'),
                    description=vuln_data.get('description', ''),
                    severity=VulnerabilitySeverity(vuln_data.get('severity', 'info')),
                    cvss_score=vuln_data.get('cvss_score'),
                    cvss_vector=vuln_data.get('cvss_vector'),
                    target=worker_task.target.value,
                    host=vuln_data.get('host'),
                    port=vuln_data.get('port'),
                    service=vuln_data.get('service'),
                    url=vuln_data.get('url'),
                    path=vuln_data.get('path'),
                    cve_id=vuln_data.get('cve_id'),
                    cwe_id=vuln_data.get('cwe_id'),
                    category=vuln_data.get('category'),
                    evidence=vuln_data.get('evidence'),
                    proof_of_concept=vuln_data.get('proof_of_concept'),
                    remediation=vuln_data.get('remediation'),
                    references=vuln_data.get('references', []),
                    tool=worker_task.worker_type.value,
                    raw_output=vuln_data,
                    exploitable=vuln_data.get('exploitable', False)
                )
                vulnerabilities.append(vulnerability)
            
            except Exception as e:
                logger.warning(f"Failed to parse vulnerability from {worker_task.worker_type}: {e}")
                continue
        
        return vulnerabilities
    
    def _deduplicate_vulnerabilities(
        self,
        vulnerabilities: List[VulnerabilityFinding]
    ) -> List[VulnerabilityFinding]:
        """
        Deduplicate vulnerabilities found by multiple tools
        
        Strategy:
        1. Group by CVE ID (if present)
        2. Group by host+port+vulnerability_id
        3. Group by similarity score
        
        Args:
            vulnerabilities: List of vulnerabilities
        
        Returns:
            Deduplicated list
        """
        if not vulnerabilities:
            return []
        
        # Group vulnerabilities by key
        groups: Dict[str, List[VulnerabilityFinding]] = defaultdict(list)
        
        for vuln in vulnerabilities:
            # Generate deduplication key
            key = self._generate_dedup_key(vuln)
            groups[key].append(vuln)
        
        # Merge grouped vulnerabilities
        deduplicated = []
        
        for key, group in groups.items():
            if len(group) == 1:
                # Single vulnerability, no merging needed
                deduplicated.append(group[0])
            else:
                # Merge multiple findings
                merged = self._merge_vulnerabilities(group)
                deduplicated.append(merged)
        
        return deduplicated
    
    def _generate_dedup_key(self, vuln: VulnerabilityFinding) -> str:
        """
        Generate deduplication key for vulnerability
        
        Args:
            vuln: Vulnerability finding
        
        Returns:
            Deduplication key
        """
        # Primary key: CVE ID
        if vuln.cve_id:
            return f"cve:{vuln.cve_id}:{vuln.host}:{vuln.port}"
        
        # Secondary key: Host + Port + Vulnerability ID
        if vuln.host:
            return f"host:{vuln.host}:{vuln.port}:{vuln.vulnerability_id}"
        
        # Tertiary key: URL + Path
        if vuln.url:
            return f"url:{vuln.url}:{vuln.path or ''}:{vuln.vulnerability_id}"
        
        # Fallback: Vulnerability ID + Target
        return f"fallback:{vuln.target}:{vuln.vulnerability_id}"
    
    def _merge_vulnerabilities(
        self,
        vulnerabilities: List[VulnerabilityFinding]
    ) -> VulnerabilityFinding:
        """
        Merge multiple vulnerability findings into one
        
        Takes the highest severity, combines evidence, merges references
        
        Args:
            vulnerabilities: List of similar vulnerabilities
        
        Returns:
            Merged vulnerability
        """
        if not vulnerabilities:
            raise ValueError("Cannot merge empty list")
        
        if len(vulnerabilities) == 1:
            return vulnerabilities[0]
        
        # Sort by severity (highest first)
        sorted_vulns = sorted(
            vulnerabilities,
            key=lambda v: self.severity_weights.get(v.severity, 0),
            reverse=True
        )
        
        # Use highest severity as base
        merged = sorted_vulns[0]
        
        # Combine evidence from all tools
        all_evidence = []
        all_tools = []
        all_references = set()
        
        for vuln in vulnerabilities:
            all_tools.append(vuln.tool)
            
            if vuln.evidence:
                all_evidence.append(f"[{vuln.tool}] {vuln.evidence}")
            
            if vuln.references:
                all_references.update(vuln.references)
        
        # Update merged vulnerability
        merged.evidence = "\n\n".join(all_evidence) if all_evidence else merged.evidence
        merged.references = sorted(list(all_references))
        merged.tool = f"Multiple tools: {', '.join(set(all_tools))}"
        
        # Take highest CVSS score
        max_cvss = max((v.cvss_score for v in vulnerabilities if v.cvss_score), default=merged.cvss_score)
        merged.cvss_score = max_cvss
        
        # Mark as exploitable if any tool found it exploitable
        merged.exploitable = any(v.exploitable for v in vulnerabilities)
        
        return merged
    
    def _count_by_severity(
        self,
        vulnerabilities: List[VulnerabilityFinding]
    ) -> Dict[VulnerabilitySeverity, int]:
        """
        Count vulnerabilities by severity
        
        Args:
            vulnerabilities: List of vulnerabilities
        
        Returns:
            Dict mapping severity to count
        """
        counts = {severity: 0 for severity in VulnerabilitySeverity}
        
        for vuln in vulnerabilities:
            counts[vuln.severity] += 1
        
        return counts
    
    def _calculate_risk_score(
        self,
        vulnerabilities: List[VulnerabilityFinding]
    ) -> float:
        """
        Calculate overall risk score
        
        Formula: Weighted sum of severity counts normalized to 0-100
        
        Args:
            vulnerabilities: List of vulnerabilities
        
        Returns:
            Risk score (0-100)
        """
        if not vulnerabilities:
            return 0.0
        
        total_score = 0.0
        
        for vuln in vulnerabilities:
            weight = self.severity_weights.get(vuln.severity, 0)
            
            # Increase weight for exploitable vulnerabilities
            if vuln.exploitable:
                weight *= 1.5
            
            total_score += weight
        
        # Normalize to 0-100 scale
        # Assume max expected is 50 vulnerabilities at critical severity
        max_expected_score = 50 * self.severity_weights[VulnerabilitySeverity.CRITICAL]
        normalized = min((total_score / max_expected_score) * 100, 100)
        
        return round(normalized, 2)
    
    def _determine_risk_level(self, risk_score: float) -> str:
        """
        Determine risk level from score
        
        Args:
            risk_score: Risk score (0-100)
        
        Returns:
            Risk level (critical, high, medium, low)
        """
        if risk_score >= 80:
            return "critical"
        elif risk_score >= 60:
            return "high"
        elif risk_score >= 30:
            return "medium"
        else:
            return "low"
    
    def _calculate_duration(self, scan_job: ScanJob) -> Optional[int]:
        """
        Calculate scan duration in seconds
        
        Args:
            scan_job: Scan job
        
        Returns:
            Duration in seconds or None
        """
        if scan_job.started_at and scan_job.completed_at:
            delta = scan_job.completed_at - scan_job.started_at
            return int(delta.total_seconds())
        
        return None
