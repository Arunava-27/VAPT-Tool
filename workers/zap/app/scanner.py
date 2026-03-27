"""
OWASP ZAP Scanner Module
Performs web application security scanning using ZAP API
"""

import time
import requests
from typing import Dict, List, Optional
from zapv2 import ZAPv2


class ZAPScanner:
    """OWASP ZAP web application scanner"""
    
    def __init__(self, zap_host: str = "localhost", zap_port: int = 8080, api_key: Optional[str] = None):
        """
        Initialize ZAP scanner
        
        Args:
            zap_host: ZAP proxy host
            zap_port: ZAP proxy port
            api_key: ZAP API key (optional)
        """
        self.zap = ZAPv2(
            apikey=api_key or "",
            proxies={
                'http': f'http://{zap_host}:{zap_port}',
                'https': f'http://{zap_host}:{zap_port}'
            }
        )
        self.zap_host = zap_host
        self.zap_port = zap_port
    
    def spider_scan(self, target: str, max_depth: int = 5, max_children: int = 10) -> str:
        """
        Run spider/crawler on target
        
        Args:
            target: Target URL
            max_depth: Maximum crawl depth
            max_children: Maximum children per node
        
        Returns:
            Scan ID
        """
        # Start spider
        scan_id = self.zap.spider.scan(target, maxdepth=max_depth, maxchildren=max_children)
        
        # Wait for spider to complete
        while int(self.zap.spider.status(scan_id)) < 100:
            time.sleep(2)
        
        return scan_id
    
    def active_scan(self, target: str, recurse: bool = True) -> str:
        """
        Run active scan on target
        
        Args:
            target: Target URL
            recurse: Scan recursively
        
        Returns:
            Scan ID
        """
        # Start active scan
        scan_id = self.zap.ascan.scan(target, recurse=recurse)
        
        # Wait for scan to complete
        while int(self.zap.ascan.status(scan_id)) < 100:
            time.sleep(5)
        
        return scan_id
    
    def passive_scan(self, target: str) -> None:
        """
        Enable passive scanning (runs automatically)
        
        Args:
            target: Target URL
        """
        # Access target to start passive scan
        self.zap.urlopen(target)
        time.sleep(2)
    
    def get_alerts(self, base_url: Optional[str] = None) -> List[Dict]:
        """
        Get all alerts/vulnerabilities found
        
        Args:
            base_url: Filter by base URL (optional)
        
        Returns:
            List of alerts
        """
        if base_url:
            return self.zap.core.alerts(baseurl=base_url)
        return self.zap.core.alerts()
    
    def full_scan(self, target: str, scan_type: str = "active", 
                  spider_config: Optional[Dict] = None,
                  scan_config: Optional[Dict] = None) -> Dict:
        """
        Perform complete scan (spider + scan + results)
        
        Args:
            target: Target URL
            scan_type: Scan type (active, passive, both)
            spider_config: Spider configuration
            scan_config: Scan configuration
        
        Returns:
            Scan results with alerts
        """
        spider_config = spider_config or {}
        scan_config = scan_config or {}
        
        results = {
            'target': target,
            'scan_type': scan_type,
            'spider_complete': False,
            'scan_complete': False,
            'alerts': []
        }
        
        try:
            # Step 1: Spider the target
            spider_scan_id = self.spider_scan(
                target,
                max_depth=spider_config.get('max_depth', 5),
                max_children=spider_config.get('max_children', 10)
            )
            results['spider_complete'] = True
            results['spider_scan_id'] = spider_scan_id
            
            # Step 2: Run active or passive scan
            if scan_type in ['active', 'both']:
                active_scan_id = self.active_scan(
                    target,
                    recurse=scan_config.get('recurse', True)
                )
                results['scan_complete'] = True
                results['active_scan_id'] = active_scan_id
            
            if scan_type in ['passive', 'both']:
                self.passive_scan(target)
                # Wait for passive scan to process
                time.sleep(5)
            
            # Step 3: Get all alerts
            results['alerts'] = self.get_alerts(base_url=target)
            results['total_alerts'] = len(results['alerts'])
            
            return results
        
        except Exception as e:
            results['error'] = str(e)
            return results
    
    def shutdown(self):
        """Shutdown ZAP (cleanup)"""
        try:
            self.zap.core.shutdown()
        except:
            pass


def run_zap_scan(target: str, scan_type: str = "active",
                spider_config: Optional[Dict] = None,
                scan_config: Optional[Dict] = None,
                zap_host: str = "localhost",
                zap_port: int = 8080,
                api_key: Optional[str] = None) -> Dict:
    """
    Run ZAP scan (convenience function)
    
    Args:
        target: Target URL
        scan_type: Scan type (active, passive, both)
        spider_config: Spider configuration
        scan_config: Scan configuration
        zap_host: ZAP host
        zap_port: ZAP port
        api_key: ZAP API key
    
    Returns:
        Scan results
    """
    scanner = ZAPScanner(zap_host, zap_port, api_key)
    return scanner.full_scan(target, scan_type, spider_config, scan_config)
