"""
Orchestrator service - Main orchestration logic
"""

from typing import List, Optional
from uuid import UUID
import logging
from datetime import datetime

from ..models.scan_models import (
    ScanRequest,
    ScanJob,
    ScanTarget,
    ScanResult,
    ScanStatus
)
from ..workflows.state_machine import WorkflowEngine
from ..dispatcher.task_dispatcher import TaskDispatcher
from ..aggregator.result_aggregator import ResultAggregator
from ..core.config import settings

logger = logging.getLogger(__name__)


class ScanOrchestrator:
    """
    Main orchestrator service that coordinates scan execution
    
    Responsibilities:
    - Create scan jobs from requests
    - Manage workflow lifecycle
    - Dispatch tasks to workers
    - Aggregate results
    - Handle errors and retries
    """
    
    def __init__(self):
        """Initialize orchestrator"""
        self.workflow_engine = WorkflowEngine()
        self.task_dispatcher = TaskDispatcher()
        self.result_aggregator = ResultAggregator()
        self.active_scans: dict[UUID, ScanJob] = {}
    
    def create_scan(self, scan_request: ScanRequest, scan_id: UUID) -> ScanJob:
        """
        Create a new scan job from request
        
        Args:
            scan_request: User scan request
            scan_id: Database scan ID
        
        Returns:
            Created scan job
        """
        logger.info(f"Creating scan job for request: {scan_request.name}")
        
        # Create scan job
        scan_job = ScanJob(
            scan_id=scan_id,
            name=scan_request.name,
            scan_type=scan_request.scan_type,
            profile=scan_request.options.profile,
            priority=scan_request.priority,
            tenant_id=scan_request.tenant_id,
            user_id=scan_request.user_id
        )
        
        # Create worker tasks
        worker_tasks = self.task_dispatcher.create_worker_tasks(
            scan_job,
            scan_request.targets
        )
        scan_job.worker_tasks = worker_tasks
        
        logger.info(f"Created scan job {scan_job.id} with {len(worker_tasks)} tasks")
        
        return scan_job
    
    def start_scan(self, scan_job: ScanJob) -> bool:
        """
        Start scan execution
        
        Args:
            scan_job: Scan job to start
        
        Returns:
            True if started successfully
        """
        logger.info(f"Starting scan {scan_job.id}")
        
        try:
            # Start workflow
            if not self.workflow_engine.start_scan(scan_job):
                return False
            
            # Prepare scan
            if not self.workflow_engine.prepare_scan(scan_job):
                return False
            
            # Transition to scanning
            if not self.workflow_engine.start_scanning(scan_job):
                return False
            
            # Dispatch tasks
            if not self.task_dispatcher.dispatch_tasks(scan_job):
                self.workflow_engine.fail_scan(scan_job, "Failed to dispatch tasks")
                return False
            
            # Track active scan
            self.active_scans[scan_job.id] = scan_job
            
            logger.info(f"Scan {scan_job.id} started successfully")
            return True
        
        except Exception as e:
            logger.error(f"Failed to start scan {scan_job.id}: {e}")
            self.workflow_engine.fail_scan(scan_job, str(e))
            return False
    
    def cancel_scan(self, scan_job_id: UUID, reason: Optional[str] = None) -> bool:
        """
        Cancel running scan
        
        Args:
            scan_job_id: Scan job ID
            reason: Optional cancellation reason
        
        Returns:
            True if cancelled
        """
        logger.info(f"Cancelling scan {scan_job_id}")
        
        scan_job = self.active_scans.get(scan_job_id)
        
        if not scan_job:
            logger.warning(f"Scan {scan_job_id} not found in active scans")
            return False
        
        try:
            # Cancel tasks
            self.task_dispatcher.cancel_tasks(scan_job_id)
            
            # Update workflow
            self.workflow_engine.cancel_scan(scan_job, reason)
            
            # Remove from active scans
            del self.active_scans[scan_job_id]
            
            logger.info(f"Scan {scan_job_id} cancelled")
            return True
        
        except Exception as e:
            logger.error(f"Failed to cancel scan {scan_job_id}: {e}")
            return False
    
    def update_scan_progress(self, scan_job: ScanJob) -> int:
        """
        Update scan progress based on task completion
        
        Args:
            scan_job: Scan job
        
        Returns:
            Progress percentage
        """
        progress = self.workflow_engine.state_machine.calculate_progress(scan_job)
        scan_job.progress_percentage = progress
        return progress
    
    def on_task_completed(
        self,
        scan_job: ScanJob,
        worker_task_id: UUID,
        result: dict
    ) -> bool:
        """
        Handle worker task completion
        
        Args:
            scan_job: Scan job
            worker_task_id: Completed worker task ID
            result: Task result
        
        Returns:
            True if handled successfully
        """
        logger.info(f"Task {worker_task_id} completed for scan {scan_job.id}")
        
        # Find and update worker task
        for task in scan_job.worker_tasks:
            if task.id == worker_task_id:
                task.status = ScanStatus.COMPLETED
                task.completed_at = datetime.utcnow()
                task.result = result
                break
        
        # Check if all tasks are complete
        all_complete = all(
            t.status in [ScanStatus.COMPLETED, ScanStatus.FAILED]
            for t in scan_job.worker_tasks
        )
        
        if all_complete:
            return self.finalize_scan(scan_job)
        
        # Update progress
        self.update_scan_progress(scan_job)
        
        return True
    
    def on_task_failed(
        self,
        scan_job: ScanJob,
        worker_task_id: UUID,
        error: str
    ) -> bool:
        """
        Handle worker task failure
        
        Args:
            scan_job: Scan job
            worker_task_id: Failed worker task ID
            error: Error message
        
        Returns:
            True if handled successfully
        """
        logger.error(f"Task {worker_task_id} failed for scan {scan_job.id}: {error}")
        
        # Find and update worker task
        for task in scan_job.worker_tasks:
            if task.id == worker_task_id:
                task.status = ScanStatus.FAILED
                task.completed_at = datetime.utcnow()
                task.error = error
                break
        
        # Check if all tasks are complete (including failures)
        all_complete = all(
            t.status in [ScanStatus.COMPLETED, ScanStatus.FAILED]
            for t in scan_job.worker_tasks
        )
        
        if all_complete:
            # Check if at least some tasks succeeded
            any_success = any(
                t.status == ScanStatus.COMPLETED
                for t in scan_job.worker_tasks
            )
            
            if any_success:
                # Partial success - finalize with available results
                return self.finalize_scan(scan_job)
            else:
                # Total failure
                self.workflow_engine.fail_scan(scan_job, "All worker tasks failed")
                return False
        
        return True
    
    def finalize_scan(self, scan_job: ScanJob) -> bool:
        """
        Finalize scan by aggregating results
        
        Args:
            scan_job: Scan job
        
        Returns:
            True if finalized successfully
        """
        logger.info(f"Finalizing scan {scan_job.id}")
        
        try:
            # Aggregate results
            scan_result = self.result_aggregator.aggregate_results(scan_job)
            
            # Complete workflow
            self.workflow_engine.complete_scan(scan_job)
            
            # Remove from active scans
            if scan_job.id in self.active_scans:
                del self.active_scans[scan_job.id]
            
            logger.info(
                f"Scan {scan_job.id} finalized: "
                f"{scan_result.total_vulnerabilities} vulnerabilities found"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to finalize scan {scan_job.id}: {e}")
            self.workflow_engine.fail_scan(scan_job, f"Finalization failed: {e}")
            return False
    
    def get_scan_status(self, scan_job_id: UUID) -> Optional[dict]:
        """
        Get current scan status
        
        Args:
            scan_job_id: Scan job ID
        
        Returns:
            Status dict or None
        """
        scan_job = self.active_scans.get(scan_job_id)
        
        if not scan_job:
            return None
        
        return {
            'id': str(scan_job.id),
            'status': scan_job.status.value,
            'progress_percentage': scan_job.progress_percentage,
            'current_phase': scan_job.current_phase,
            'vulnerabilities_found': scan_job.vulnerabilities_found,
            'tasks_total': len(scan_job.worker_tasks),
            'tasks_completed': sum(
                1 for t in scan_job.worker_tasks
                if t.status in [ScanStatus.COMPLETED, ScanStatus.FAILED]
            ),
            'error': scan_job.error
        }
