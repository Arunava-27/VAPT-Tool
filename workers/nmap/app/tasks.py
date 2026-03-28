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
    
    start_time = time.time()
    
    try:
        # Validate input
        if not target:
            raise TaskError("Target is required", ErrorCategory.INVALID_INPUT)
        
        base_task.log_start(self.request.id, target, "nmap")
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
        
        base_task.log_success(self.request.id, duration, "nmap")
        return result
    
    except TaskError as e:
        # Categorized error
        base_task.log_error(self.request.id, e, e.category, "nmap")
        
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