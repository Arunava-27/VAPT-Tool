"""
Trivy Scanner Module
Performs container, filesystem, and infrastructure-as-code security scanning
"""

import subprocess
import json
from typing import Dict, List, Optional
from enum import Enum


class ScanTarget(Enum):
    """Trivy scan target types"""
    IMAGE = "image"
    FILESYSTEM = "fs"
    REPOSITORY = "repo"
    CONFIG = "config"


class TrivyScanner:
    """Aqua Security Trivy vulnerability scanner"""
    
    @staticmethod
    def scan_image(image: str, severities: Optional[List[str]] = None,
                  scanners: Optional[List[str]] = None) -> Dict:
        """
        Scan Docker/container image
        
        Args:
            image: Image name/tag (e.g., alpine:3.15)
            severities: List of severities to report (CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN)
            scanners: List of scanners to use (vuln, secret, config)
        
        Returns:
            Scan results as dictionary
        """
        severities = severities or ["CRITICAL", "HIGH", "MEDIUM"]
        scanners = scanners or ["vuln"]
        
        command = [
            "trivy",
            "image",
            "--format", "json",
            "--severity", ",".join(severities),
            "--scanners", ",".join(scanners),
            image
        ]
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            raise Exception(f"Trivy scan failed: {result.stderr}")
        
        return json.loads(result.stdout)
    
    @staticmethod
    def scan_filesystem(path: str, severities: Optional[List[str]] = None,
                       scanners: Optional[List[str]] = None) -> Dict:
        """
        Scan filesystem path
        
        Args:
            path: Filesystem path to scan
            severities: List of severities to report
            scanners: List of scanners to use
        
        Returns:
            Scan results as dictionary
        """
        severities = severities or ["CRITICAL", "HIGH", "MEDIUM"]
        scanners = scanners or ["vuln", "secret", "config"]
        
        command = [
            "trivy",
            "fs",
            "--format", "json",
            "--severity", ",".join(severities),
            "--scanners", ",".join(scanners),
            path
        ]
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            raise Exception(f"Trivy filesystem scan failed: {result.stderr}")
        
        return json.loads(result.stdout)
    
    @staticmethod
    def scan_repository(repo_url: str, severities: Optional[List[str]] = None,
                       scanners: Optional[List[str]] = None) -> Dict:
        """
        Scan Git repository
        
        Args:
            repo_url: Git repository URL
            severities: List of severities to report
            scanners: List of scanners to use
        
        Returns:
            Scan results as dictionary
        """
        severities = severities or ["CRITICAL", "HIGH", "MEDIUM"]
        scanners = scanners or ["vuln", "secret", "config"]
        
        command = [
            "trivy",
            "repo",
            "--format", "json",
            "--severity", ",".join(severities),
            "--scanners", ",".join(scanners),
            repo_url
        ]
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if result.returncode != 0:
            raise Exception(f"Trivy repository scan failed: {result.stderr}")
        
        return json.loads(result.stdout)
    
    @staticmethod
    def scan_config(path: str, config_type: Optional[str] = None) -> Dict:
        """
        Scan IaC configuration files
        
        Args:
            path: Path to config files
            config_type: Config type (terraform, cloudformation, dockerfile, kubernetes)
        
        Returns:
            Scan results as dictionary
        """
        command = [
            "trivy",
            "config",
            "--format", "json",
            path
        ]
        
        if config_type:
            command.extend(["--file-patterns", f"**/*.{config_type}"])
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode != 0:
            raise Exception(f"Trivy config scan failed: {result.stderr}")
        
        return json.loads(result.stdout)


def run_trivy_scan(target: str, scan_type: str = "image",
                  severities: Optional[List[str]] = None,
                  scanners: Optional[List[str]] = None,
                  options: Optional[Dict] = None) -> Dict:
    """
    Run Trivy scan (convenience function)
    
    Args:
        target: Target to scan (image name, path, or URL)
        scan_type: Type of scan (image, filesystem, repository, config)
        severities: List of severities to report
        scanners: List of scanners to use
        options: Additional options
    
    Returns:
        Scan results
    """
    options = options or {}
    
    if scan_type == ScanTarget.IMAGE.value:
        return TrivyScanner.scan_image(target, severities, scanners)
    elif scan_type == ScanTarget.FILESYSTEM.value:
        return TrivyScanner.scan_filesystem(target, severities, scanners)
    elif scan_type == ScanTarget.REPOSITORY.value:
        return TrivyScanner.scan_repository(target, severities, scanners)
    elif scan_type == ScanTarget.CONFIG.value:
        return TrivyScanner.scan_config(target, options.get('config_type'))
    else:
        raise ValueError(f"Invalid scan type: {scan_type}")
