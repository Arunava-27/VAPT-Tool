import logging
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'base'))

from .config import celery_app
from .scanner import run_metasploit_scan
from base_task import BaseTask, ErrorCategory, TaskError
from result_parser import MetasploitResultParser

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

base_task = BaseTask()


@celery_app.task(name="metasploit.scan", bind=True)
def metasploit_scan(self, task_data):
    """
    Metasploit exploitation/verification task
    
    Args:
        task_data: Dictionary containing:
            - target: Target host/IP (required)
            - scan_type: Type (verify, auxiliary, exploit)
            - options: Module and connection options
    
    Returns:
        Standardized result dictionary
    """
    target = task_data.get("target")
    scan_type = task_data.get("scan_type", "verify")
    options = task_data.get("options", {})
    
    start_time = time.time()
    
    try:
        if not target:
            raise TaskError("Target is required", ErrorCategory.INVALID_INPUT)
        
        base_task.log_start(self.request.id, target, "metasploit")
        base_task.log_progress(self.request.id, f"Scan type: {scan_type}", "metasploit")
        
        # Safety check for exploit mode
        if scan_type == "exploit" and not options.get('safe_mode', True):
            base_task.log_progress(self.request.id, 
                                  "⚠️ WARNING: Running in exploit mode (not safe_mode)", 
                                  "metasploit")
        
        # Run Metasploit scan with retry logic
        def run_scan():
            return run_metasploit_scan(target, scan_type, options)
        
        msf_results = base_task.with_retry(
            run_scan,
            max_retries=options.get('max_retries', 1),
            task_id=self.request.id,
            tool="metasploit"
        )
        
        base_task.log_progress(self.request.id, "Scan completed, parsing results", "metasploit")
        
        # Convert to standardized format
        # Note: Metasploit results vary widely, using generic structure
        standardized_result = MetasploitResultParser.parse(
            {'vulnerabilities': [msf_results]}, 
            target
        )
        
        # Create final result
        duration = time.time() - start_time
        result = base_task.create_result(
            status='completed',
            task_id=self.request.id,
            tool='metasploit',
            target=target,
            result_data=standardized_result,
            error=None,
            metadata={
                'scan_type': scan_type,
                'safe_mode': options.get('safe_mode', True),
                'duration': duration,
                'raw_result': msf_results
            }
        )
        
        if not base_task.validate_result(result):
            raise TaskError("Result validation failed", ErrorCategory.TOOL_ERROR)
        
        base_task.log_success(self.request.id, duration, "metasploit")
        return result
    
    except TaskError as e:
        base_task.log_error(self.request.id, e, e.category, "metasploit")
        
        return base_task.create_result(
            status='failed',
            task_id=self.request.id,
            tool='metasploit',
            target=target,
            result_data=None,
            error=str(e),
            metadata={
                'error_category': e.category.value,
                'duration': time.time() - start_time
            }
        )
    
    except Exception as e:
        category = base_task.categorize_error(e)
        base_task.log_error(self.request.id, e, category, "metasploit")
        
        return base_task.create_result(
            status='failed',
            task_id=self.request.id,
            tool='metasploit',
            target=target,
            result_data=None,
            error=str(e),
            metadata={
                'error_category': category.value,
                'duration': time.time() - start_time
            }
        )
