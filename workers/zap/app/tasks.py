import logging
import time
import sys
import os

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'base'))

from .config import celery_app
from .scanner import run_zap_scan
from base_task import BaseTask, ErrorCategory, TaskError
from result_parser import ZAPResultParser

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

base_task = BaseTask()


@celery_app.task(name="zap.scan", bind=True)
def zap_scan(self, task_data):
    """
    OWASP ZAP web vulnerability scan task
    
    Args:
        task_data: Dictionary containing:
            - target: Target URL (required)
            - scan_type: Scan type (active, passive, both) - default: active
            - spider_config: Spider configuration (optional)
            - scan_config: Scan configuration (optional)
    
    Returns:
        Standardized result dictionary
    """
    target = task_data.get("target")
    scan_type = task_data.get("scan_type", "active")
    spider_config = task_data.get("spider_config", {})
    scan_config = task_data.get("scan_config", {})
    options = task_data.get("options", {})
    
    start_time = time.time()
    
    try:
        # Validate input
        if not target:
            raise TaskError("Target URL is required", ErrorCategory.INVALID_INPUT)
        
        if not target.startswith(('http://', 'https://')):
            raise TaskError("Target must be a valid HTTP(S) URL", ErrorCategory.INVALID_INPUT)
        
        base_task.log_start(self.request.id, target, "zap")
        base_task.log_progress(self.request.id, f"Scan type: {scan_type}", "zap")
        
        # Run ZAP scan with retry logic
        def run_scan():
            return run_zap_scan(
                target,
                scan_type,
                spider_config,
                scan_config,
                zap_host=options.get('zap_host', 'localhost'),
                zap_port=options.get('zap_port', 8080),
                api_key=options.get('api_key')
            )
        
        zap_results = base_task.with_retry(
            run_scan,
            max_retries=options.get('max_retries', 2),
            task_id=self.request.id,
            tool="zap"
        )
        
        base_task.log_progress(self.request.id, "Scan completed, parsing results", "zap")
        
        # Convert to standardized format
        standardized_result = ZAPResultParser.parse(zap_results, target)
        
        base_task.log_progress(self.request.id,
                              f"Found {standardized_result['summary']['total_findings']} vulnerabilities",
                              "zap")
        
        # Create final result
        duration = time.time() - start_time
        result = base_task.create_result(
            status='completed',
            task_id=self.request.id,
            tool='zap',
            target=target,
            result_data=standardized_result,
            error=None,
            metadata={
                'scan_type': scan_type,
                'duration': duration,
                'spider_complete': zap_results.get('spider_complete', False),
                'scan_complete': zap_results.get('scan_complete', False)
            }
        )
        
        if not base_task.validate_result(result):
            raise TaskError("Result validation failed", ErrorCategory.TOOL_ERROR)
        
        base_task.log_success(self.request.id, duration, "zap")
        return result
    
    except TaskError as e:
        base_task.log_error(self.request.id, e, e.category, "zap")
        
        return base_task.create_result(
            status='failed',
            task_id=self.request.id,
            tool='zap',
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
        base_task.log_error(self.request.id, e, category, "zap")
        
        return base_task.create_result(
            status='failed',
            task_id=self.request.id,
            tool='zap',
            target=target,
            result_data=None,
            error=str(e),
            metadata={
                'error_category': category.value,
                'duration': time.time() - start_time
            }
        )
