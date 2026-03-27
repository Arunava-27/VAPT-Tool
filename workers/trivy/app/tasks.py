import logging
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'base'))

from .config import celery_app
from .scanner import run_trivy_scan
from base_task import BaseTask, ErrorCategory, TaskError
from result_parser import TrivyResultParser

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

base_task = BaseTask()


@celery_app.task(name="trivy.scan", bind=True)
def trivy_scan(self, task_data):
    """
    Trivy container/infrastructure scan task
    
    Args:
        task_data: Dictionary containing:
            - target: Target to scan (required)
            - scan_type: Type (image, filesystem, repository, config)
            - severities: List of severities (CRITICAL, HIGH, MEDIUM, LOW)
            - scanners: List of scanners (vuln, secret, config)
    
    Returns:
        Standardized result dictionary
    """
    target = task_data.get("target")
    scan_type = task_data.get("scan_type", "image")
    severities = task_data.get("severities", ["CRITICAL", "HIGH", "MEDIUM"])
    scanners = task_data.get("scanners", ["vuln"])
    options = task_data.get("options", {})
    
    start_time = time.time()
    
    try:
        if not target:
            raise TaskError("Target is required", ErrorCategory.INVALID_INPUT)
        
        base_task.log_start(self.request.id, target, "trivy")
        base_task.log_progress(self.request.id, f"Scan type: {scan_type}", "trivy")
        
        # Run Trivy scan with retry logic
        def run_scan():
            return run_trivy_scan(target, scan_type, severities, scanners, options)
        
        trivy_results = base_task.with_retry(
            run_scan,
            max_retries=options.get('max_retries', 2),
            task_id=self.request.id,
            tool="trivy"
        )
        
        base_task.log_progress(self.request.id, "Scan completed, parsing results", "trivy")
        
        # Convert to standardized format
        standardized_result = TrivyResultParser.parse(trivy_results, target)
        
        base_task.log_progress(self.request.id,
                              f"Found {standardized_result['summary']['total_findings']} vulnerabilities",
                              "trivy")
        
        # Create final result
        duration = time.time() - start_time
        result = base_task.create_result(
            status='completed',
            task_id=self.request.id,
            tool='trivy',
            target=target,
            result_data=standardized_result,
            error=None,
            metadata={
                'scan_type': scan_type,
                'severities': severities,
                'scanners': scanners,
                'duration': duration
            }
        )
        
        if not base_task.validate_result(result):
            raise TaskError("Result validation failed", ErrorCategory.TOOL_ERROR)
        
        base_task.log_success(self.request.id, duration, "trivy")
        return result
    
    except TaskError as e:
        base_task.log_error(self.request.id, e, e.category, "trivy")
        
        return base_task.create_result(
            status='failed',
            task_id=self.request.id,
            tool='trivy',
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
        base_task.log_error(self.request.id, e, category, "trivy")
        
        return base_task.create_result(
            status='failed',
            task_id=self.request.id,
            tool='trivy',
            target=target,
            result_data=None,
            error=str(e),
            metadata={
                'error_category': category.value,
                'duration': time.time() - start_time
            }
        )
