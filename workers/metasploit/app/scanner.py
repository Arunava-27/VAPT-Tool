"""
Metasploit Scanner Module
Performs exploitation testing and vulnerability verification
"""

from typing import Dict, List, Optional
from pymetasploit3.msfrpc import MsfRpcClient
import time


class MetasploitScanner:
    """Metasploit Framework exploitation scanner"""
    
    def __init__(self, password: str = "msf", server: str = "127.0.0.1", 
                 port: int = 55553, ssl: bool = True):
        """
        Initialize Metasploit RPC client
        
        Args:
            password: MSF RPC password
            server: MSF RPC server address
            port: MSF RPC port
            ssl: Use SSL connection
        """
        self.client = MsfRpcClient(password, server=server, port=port, ssl=ssl)
        self.console = self.client.consoles.console()
    
    def run_auxiliary_scan(self, module: str, options: Dict) -> Dict:
        """
        Run auxiliary/scanner module
        
        Args:
            module: Module path (e.g., scanner/portscan/tcp)
            options: Module options (RHOSTS, PORTS, etc.)
        
        Returns:
            Scan results
        """
        # Load module
        aux = self.client.modules.use('auxiliary', module)
        
        # Set options
        for key, value in options.items():
            aux[key] = value
        
        # Execute
        aux.execute()
        
        # Wait for completion (check job status)
        time.sleep(5)
        
        # Get results
        output = self.console.read()
        
        return {
            'module': module,
            'options': options,
            'output': output,
            'status': 'completed'
        }
    
    def run_exploit(self, module: str, payload: str, options: Dict, 
                   safe_mode: bool = True) -> Dict:
        """
        Run exploit module (use with caution!)
        
        Args:
            module: Exploit module path
            payload: Payload to use
            options: Module options
            safe_mode: Only check if exploitable, don't actually exploit
        
        Returns:
            Exploitation results
        """
        if safe_mode:
            # Only check, don't exploit
            return {
                'module': module,
                'payload': payload,
                'status': 'check_only',
                'message': 'Safe mode enabled - exploitation not performed',
                'exploitable': 'unknown'
            }
        
        # WARNING: Actual exploitation - use with extreme caution
        exploit = self.client.modules.use('exploit', module)
        exploit['PAYLOAD'] = payload
        
        for key, value in options.items():
            exploit[key] = value
        
        # Execute exploit
        result = exploit.execute()
        
        return {
            'module': module,
            'payload': payload,
            'options': options,
            'result': result,
            'status': 'exploited' if result else 'failed'
        }
    
    def search_exploits(self, target: str, service: Optional[str] = None) -> List[Dict]:
        """
        Search for applicable exploits
        
        Args:
            target: Target description or service name
            service: Specific service name
        
        Returns:
            List of matching exploits
        """
        search_term = service if service else target
        results = self.client.modules.search(search_term)
        
        exploits = []
        for result in results:
            if result['type'] == 'exploit':
                exploits.append({
                    'name': result['name'],
                    'type': result['type'],
                    'rank': result.get('rank', 'unknown'),
                    'description': result.get('description', '')
                })
        
        return exploits
    
    def verify_vulnerability(self, host: str, port: int, service: str, 
                           cve_id: Optional[str] = None) -> Dict:
        """
        Verify if target is vulnerable (safe check only)
        
        Args:
            host: Target host
            port: Target port
            service: Service name
            cve_id: CVE ID if known
        
        Returns:
            Verification results
        """
        # Search for relevant modules
        exploits = self.search_exploits(target=service, service=service)
        
        if not exploits:
            return {
                'vulnerable': False,
                'message': f'No exploits found for {service}',
                'exploits': []
            }
        
        return {
            'vulnerable': 'possible',
            'message': f'Found {len(exploits)} potential exploits for {service}',
            'exploits': exploits[:5],  # Return top 5
            'recommendation': 'Manual verification recommended'
        }
    
    def close(self):
        """Clean up resources"""
        try:
            self.console.destroy()
        except:
            pass


def run_metasploit_scan(target: str, scan_type: str = "verify",
                       options: Optional[Dict] = None) -> Dict:
    """
    Run Metasploit scan (convenience function)
    
    Args:
        target: Target host/IP
        scan_type: Type of scan (verify, auxiliary, exploit)
        options: Additional options
    
    Returns:
        Scan results
    """
    options = options or {}
    
    try:
        scanner = MetasploitScanner(
            password=options.get('msf_password', 'msf'),
            server=options.get('msf_server', '127.0.0.1'),
            port=options.get('msf_port', 55553),
            ssl=options.get('msf_ssl', True)
        )
        
        if scan_type == "verify":
            # Safe vulnerability verification
            result = scanner.verify_vulnerability(
                host=target,
                port=options.get('port', 0),
                service=options.get('service', ''),
                cve_id=options.get('cve_id')
            )
        
        elif scan_type == "auxiliary":
            # Run auxiliary scanner
            result = scanner.run_auxiliary_scan(
                module=options.get('module', 'scanner/portscan/tcp'),
                options={'RHOSTS': target, **options.get('module_options', {})}
            )
        
        elif scan_type == "exploit":
            # Exploitation (safe mode by default)
            result = scanner.run_exploit(
                module=options.get('module', ''),
                payload=options.get('payload', ''),
                options={'RHOSTS': target, **options.get('module_options', {})},
                safe_mode=options.get('safe_mode', True)
            )
        
        else:
            raise ValueError(f"Invalid scan type: {scan_type}")
        
        scanner.close()
        return result
    
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'target': target
        }
