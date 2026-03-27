"""
Prowler Scanner Module
Performs cloud security assessments for AWS, Azure, and GCP
"""

import subprocess
import json
from typing import Dict, List, Optional
from enum import Enum


class CloudProvider(Enum):
    """Supported cloud providers"""
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


class ProwlerScanner:
    """Prowler cloud security assessment scanner"""
    
    @staticmethod
    def scan_aws(profile: Optional[str] = None, regions: Optional[List[str]] = None,
                services: Optional[List[str]] = None, severity: Optional[List[str]] = None) -> List[Dict]:
        """
        Scan AWS account
        
        Args:
            profile: AWS profile name (uses default if not specified)
            regions: List of AWS regions (all regions if not specified)
            services: List of AWS services to scan (all if not specified)
            severity: Filter by severity (critical, high, medium, low)
        
        Returns:
            List of findings
        """
        command = [
            "prowler",
            "aws",
            "--output-modes", "json"
        ]
        
        if profile:
            command.extend(["--profile", profile])
        
        if regions:
            command.extend(["--region", ",".join(regions)])
        
        if services:
            command.extend(["--services", ",".join(services)])
        
        if severity:
            command.extend(["--severity", ",".join(severity)])
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutes
        )
        
        if result.returncode != 0:
            raise Exception(f"Prowler AWS scan failed: {result.stderr}")
        
        # Parse JSON output from stdout
        return ProwlerScanner._parse_output(result.stdout)
    
    @staticmethod
    def scan_azure(subscription_id: Optional[str] = None,
                  services: Optional[List[str]] = None,
                  severity: Optional[List[str]] = None) -> List[Dict]:
        """
        Scan Azure subscription
        
        Args:
            subscription_id: Azure subscription ID
            services: List of Azure services to scan
            severity: Filter by severity
        
        Returns:
            List of findings
        """
        command = [
            "prowler",
            "azure",
            "--output-modes", "json"
        ]
        
        if subscription_id:
            command.extend(["--subscription-id", subscription_id])
        
        if services:
            command.extend(["--services", ",".join(services)])
        
        if severity:
            command.extend(["--severity", ",".join(severity)])
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=1800
        )
        
        if result.returncode != 0:
            raise Exception(f"Prowler Azure scan failed: {result.stderr}")
        
        return ProwlerScanner._parse_output(result.stdout)
    
    @staticmethod
    def scan_gcp(project_id: Optional[str] = None,
                services: Optional[List[str]] = None,
                severity: Optional[List[str]] = None) -> List[Dict]:
        """
        Scan GCP project
        
        Args:
            project_id: GCP project ID
            services: List of GCP services to scan
            severity: Filter by severity
        
        Returns:
            List of findings
        """
        command = [
            "prowler",
            "gcp",
            "--output-modes", "json"
        ]
        
        if project_id:
            command.extend(["--project-id", project_id])
        
        if services:
            command.extend(["--services", ",".join(services)])
        
        if severity:
            command.extend(["--severity", ",".join(severity)])
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=1800
        )
        
        if result.returncode != 0:
            raise Exception(f"Prowler GCP scan failed: {result.stderr}")
        
        return ProwlerScanner._parse_output(result.stdout)
    
    @staticmethod
    def _parse_output(output: str) -> List[Dict]:
        """
        Parse Prowler JSON output
        
        Args:
            output: Raw stdout from Prowler
        
        Returns:
            List of findings as dictionaries
        """
        findings = []
        
        # Prowler outputs one JSON object per line
        for line in output.strip().split('\n'):
            if line.strip():
                try:
                    finding = json.loads(line)
                    findings.append(finding)
                except json.JSONDecodeError:
                    continue
        
        return findings


def run_prowler_scan(target: str, cloud_provider: str = "aws",
                    regions: Optional[List[str]] = None,
                    services: Optional[List[str]] = None,
                    severity: Optional[List[str]] = None,
                    credentials: Optional[Dict] = None) -> List[Dict]:
    """
    Run Prowler cloud security scan (convenience function)
    
    Args:
        target: Target identifier (profile name, subscription ID, project ID)
        cloud_provider: Cloud provider (aws, azure, gcp)
        regions: List of regions (AWS only)
        services: List of services to scan
        severity: Filter by severity
        credentials: Cloud credentials (optional, uses environment if not provided)
    
    Returns:
        List of findings
    """
    credentials = credentials or {}
    
    if cloud_provider == CloudProvider.AWS.value:
        return ProwlerScanner.scan_aws(
            profile=target if target else None,
            regions=regions,
            services=services,
            severity=severity
        )
    elif cloud_provider == CloudProvider.AZURE.value:
        return ProwlerScanner.scan_azure(
            subscription_id=target if target else None,
            services=services,
            severity=severity
        )
    elif cloud_provider == CloudProvider.GCP.value:
        return ProwlerScanner.scan_gcp(
            project_id=target if target else None,
            services=services,
            severity=severity
        )
    else:
        raise ValueError(f"Unsupported cloud provider: {cloud_provider}")
