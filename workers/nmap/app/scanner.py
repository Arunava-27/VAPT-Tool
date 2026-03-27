import subprocess
from typing import Dict, List, Optional
from enum import Enum


class ScanProfile(Enum):
    """Predefined scan profiles for different use cases"""
    QUICK = "quick"
    COMPREHENSIVE = "comprehensive"
    STEALTH = "stealth"
    CUSTOM = "custom"


class NmapScanner:
    """Enhanced Nmap scanner with multiple scan profiles"""
    
    DEFAULT_TIMEOUT = 60
    DEFAULT_HOST_TIMEOUT = "30s"
    DEFAULT_PORT_RANGE = "1-1000"
    
    @staticmethod
    def get_scan_command(target: str, profile: str = "quick", 
                        ports: Optional[str] = None,
                        options: Optional[Dict] = None) -> List[str]:
        """
        Build Nmap command based on scan profile
        
        Args:
            target: Target to scan (IP, hostname, or CIDR)
            profile: Scan profile (quick, comprehensive, stealth, custom)
            ports: Port specification (e.g., "80,443,8080" or "1-65535")
            options: Additional custom options
        
        Returns:
            Command list for subprocess
        """
        options = options or {}
        ports = ports or NmapScanner.DEFAULT_PORT_RANGE
        
        # Base command
        command = ["nmap"]
        
        # Profile-specific settings
        if profile == ScanProfile.QUICK.value:
            # Quick scan: Fast, limited ports, no version detection
            command.extend([
                "-F",  # Fast scan (100 most common ports)
                "-T4",  # Aggressive timing
                "--host-timeout", options.get("host_timeout", "30s"),
            ])
        
        elif profile == ScanProfile.COMPREHENSIVE.value:
            # Comprehensive scan: Version detection, OS detection, scripts
            command.extend([
                "-A",  # Aggressive scan (OS detection, version, scripts, traceroute)
                "-T4",  # Aggressive timing
                "-p", ports,
                "--host-timeout", options.get("host_timeout", "300s"),
                "--script", options.get("scripts", "default,vuln"),
            ])
        
        elif profile == ScanProfile.STEALTH.value:
            # Stealth scan: SYN scan, slow timing, fragmentation
            command.extend([
                "-sS",  # SYN stealth scan
                "-T2",  # Polite timing
                "-f",   # Fragment packets
                "-p", ports,
                "--host-timeout", options.get("host_timeout", "120s"),
                "-D", "RND:5",  # Decoy scan with 5 random IPs
            ])
        
        else:  # custom
            # Custom scan: Use provided options
            if "scan_type" in options:
                command.append(options["scan_type"])  # e.g., -sT, -sS, -sU
            else:
                command.append("-sT")  # Default to TCP connect scan
            
            command.extend([
                "-p", ports,
                "--host-timeout", options.get("host_timeout", "60s"),
            ])
            
            if options.get("version_detection"):
                command.append("-sV")
            
            if options.get("os_detection"):
                command.append("-O")
            
            if options.get("scripts"):
                command.extend(["--script", options["scripts"]])
            
            if options.get("timing"):
                command.append(options["timing"])  # e.g., -T4
        
        # Always output XML
        command.extend(["-oX", "-"])
        
        # Add target
        command.append(target)
        
        return command
    
    @staticmethod
    def run_scan(target: str, profile: str = "quick", 
                ports: Optional[str] = None,
                options: Optional[Dict] = None,
                timeout: int = 60) -> str:
        """
        Execute Nmap scan
        
        Args:
            target: Target to scan
            profile: Scan profile
            ports: Port specification
            options: Additional options
            timeout: Execution timeout in seconds
        
        Returns:
            XML output string
        
        Raises:
            Exception: If scan fails
        """
        command = NmapScanner.get_scan_command(target, profile, ports, options)
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode != 0:
            raise Exception(f"Nmap scan failed: {result.stderr}")
        
        return result.stdout


def run_nmap_scan(target: str, profile: str = "quick", 
                 ports: Optional[str] = None,
                 options: Optional[Dict] = None) -> str:
    """
    Legacy function for backwards compatibility
    
    Args:
        target: Target to scan
        profile: Scan profile (quick, comprehensive, stealth, custom)
        ports: Port range
        options: Additional options
    
    Returns:
        XML output
    """
    return NmapScanner.run_scan(target, profile, ports, options)