import logging
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'base'))

from .config import celery_app
from .scanner import run_prowler_scan
from base_task import BaseTask, ErrorCategory, TaskError
from result_parser import ProwlerResultParser

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

base_task = BaseTask()


@celery_app.task(name="prowler.scan", bind=True)
def prowler_scan(self, task_data):
    """
    Prowler cloud security assessment task
    
    Args:
        task_data: Dictionary containing:
            - target: Target (AWS profile/Azure subscription/GCP project)
            - cloud_provider: Provider (aws, azure, gcp)
            - regions: List of regions (AWS only)
            - services: List of services to scan
            - severity: Filter by severity
    
    Returns:
        Standardized result dictionary
    """
    target = task_data.get("target", "default")
    cloud_provider = task_data.get("cloud_provider", "aws")
    regions = task_data.get("regions")
    services = task_data.get("services")
    severity = task_data.get("severity", ["critical", "high"])
    credentials = task_data.get("credentials", {})
    options = task_data.get("options", {})
    
    start_time = time.time()
    
    try:
        base_task.log_start(self.request.id, f"{cloud_provider}:{target}", "prowler")
        base_task.log_progress(self.request.id, f"Scanning {cloud_provider.upper()}", "prowler")
        
        # Run Prowler scan with retry logic
        def run_scan():
            return run_prowler_scan(
                target,
                cloud_provider,
                regions,
                services,
                severity,
                credentials
            )
        
        prowler_results = base_task.with_retry(
            run_scan,
            max_retries=options.get('max_retries', 1),  # Cloud scans take long, limit retries
            task_id=self.request.id,
            tool="prowler"
        )
        
        base_task.log_progress(self.request.id, "Scan completed, parsing results", "prowler")
        
        # Convert to standardized format
        standardized_result = ProwlerResultParser.parse(prowler_results, target)
        
        base_task.log_progress(self.request.id,
                              f"Found {standardized_result['summary']['total_findings']} findings",
                              "prowler")
        
        # Create final result
        duration = time.time() - start_time
        result = base_task.create_result(
            status='completed',
            task_id=self.request.id,
            tool='prowler',
            target=f"{cloud_provider}:{target}",
            result_data=standardized_result,
            error=None,
            metadata={
                'cloud_provider': cloud_provider,
                'regions': regions,
                'services': services,
                'severity': severity,
                'duration': duration
            }
        )
        
        if not base_task.validate_result(result):
            raise TaskError("Result validation failed", ErrorCategory.TOOL_ERROR)
        
        base_task.log_success(self.request.id, duration, "prowler")
        return result
    
    except TaskError as e:
        base_task.log_error(self.request.id, e, e.category, "prowler")
        
        return base_task.create_result(
            status='failed',
            task_id=self.request.id,
            tool='prowler',
            target=f"{cloud_provider}:{target}",
            result_data=None,
            error=str(e),
            metadata={
                'error_category': e.category.value,
                'duration': time.time() - start_time
            }
        )
    
    except Exception as e:
        category = base_task.categorize_error(e)
        base_task.log_error(self.request.id, e, category, "prowler")
        
        return base_task.create_result(
            status='failed',
            task_id=self.request.id,
            tool='prowler',
            target=f"{cloud_provider}:{target}",
            result_data=None,
            error=str(e),
            metadata={
                'error_category': category.value,
                'duration': time.time() - start_time
            }
        )
