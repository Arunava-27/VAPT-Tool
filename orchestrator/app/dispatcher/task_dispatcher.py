"""
Task dispatcher - Routes scan tasks to appropriate workers
"""

from typing import Dict, List, Optional, Set
from uuid import UUID
import logging
from celery import group, chord

from ..models.scan_models import (
    ScanType,
    ScanProfile,
    ScanJob,
    WorkerTask,
    WorkerType,
    ScanTarget,
    ScanStatus
)
from ..core.config import settings

logger = logging.getLogger(__name__)


class TaskDispatcher:
    """
    Dispatches scan tasks to appropriate Celery workers
    """
    
    # Map scan types to required workers
    SCAN_TYPE_WORKERS: Dict[ScanType, List[WorkerType]] = {
        ScanType.NETWORK: [WorkerType.NMAP],
        ScanType.WEB: [WorkerType.ZAP, WorkerType.NMAP],
        ScanType.CONTAINER: [WorkerType.TRIVY],
        ScanType.CLOUD: [WorkerType.PROWLER],
        ScanType.COMPREHENSIVE: [
            WorkerType.NMAP,
            WorkerType.ZAP,
            WorkerType.TRIVY,
            WorkerType.PROWLER
        ],
        ScanType.CUSTOM: []  # Determined dynamically
    }
    
    # Map target types to appropriate workers
    TARGET_TYPE_WORKERS: Dict[str, List[WorkerType]] = {
        "ip": [WorkerType.NMAP],
        "cidr": [WorkerType.NMAP],
        "domain": [WorkerType.NMAP, WorkerType.ZAP],
        "url": [WorkerType.ZAP],
        "container_image": [WorkerType.TRIVY],
        "cloud_account": [WorkerType.PROWLER],
        "host": [WorkerType.NMAP]
    }
    
    def __init__(self):
        """Initialize task dispatcher"""
        self.active_tasks: Dict[UUID, List[str]] = {}  # scan_job_id -> [celery_task_ids]
    
    def create_worker_tasks(
        self,
        scan_job: ScanJob,
        targets: List[ScanTarget]
    ) -> List[WorkerTask]:
        """
        Create worker tasks based on scan type and targets
        
        Args:
            scan_job: Scan job
            targets: List of scan targets
        
        Returns:
            List of worker tasks to execute
        """
        worker_tasks: List[WorkerTask] = []
        
        # Determine which workers to use
        if scan_job.scan_type == ScanType.CUSTOM:
            workers = self._determine_workers_for_targets(targets)
        else:
            workers = self.SCAN_TYPE_WORKERS.get(scan_job.scan_type, [])
        
        if not workers:
            logger.warning(f"No workers determined for scan type {scan_job.scan_type}")
            return []
        
        # Create tasks for each worker-target combination
        for target in targets:
            for worker_type in workers:
                # Check if worker is suitable for this target
                if self._is_worker_suitable(worker_type, target):
                    task = WorkerTask(
                        worker_type=worker_type,
                        target=target,
                        options=self._build_worker_options(
                            worker_type,
                            scan_job.profile,
                            target
                        )
                    )
                    worker_tasks.append(task)
        
        logger.info(
            f"Created {len(worker_tasks)} worker tasks for scan {scan_job.id}"
        )
        
        return worker_tasks
    
    def dispatch_tasks(self, scan_job: ScanJob) -> bool:
        """
        Dispatch worker tasks to Celery queue
        
        Args:
            scan_job: Scan job with worker tasks
        
        Returns:
            True if dispatched successfully
        """
        if not scan_job.worker_tasks:
            logger.error(f"No worker tasks to dispatch for scan {scan_job.id}")
            return False
        
        try:
            celery_task_ids = []
            
            # Dispatch tasks based on parallel execution settings
            if settings.PARALLEL_SCAN_ENABLED and len(scan_job.worker_tasks) > 1:
                celery_task_ids = self._dispatch_parallel(scan_job)
            else:
                celery_task_ids = self._dispatch_sequential(scan_job)
            
            # Track active tasks
            self.active_tasks[scan_job.id] = celery_task_ids
            
            logger.info(
                f"Dispatched {len(celery_task_ids)} tasks for scan {scan_job.id}"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to dispatch tasks for scan {scan_job.id}: {e}")
            return False
    
    def _dispatch_parallel(self, scan_job: ScanJob) -> List[str]:
        """
        Dispatch tasks in parallel using Celery group
        
        Args:
            scan_job: Scan job
        
        Returns:
            List of Celery task IDs
        """
        from ..services.celery_app import celery_app
        
        celery_tasks = []
        task_ids = []
        
        # Build Celery task signatures
        for worker_task in scan_job.worker_tasks:
            task_name = f"{worker_task.worker_type.value}.scan"
            queue_name = worker_task.worker_type.value

            task_data = {
                "scan_id": str(scan_job.id),
                "worker_task_id": str(worker_task.id),
                "target": worker_task.target.value,
                "target_type": worker_task.target.type,
                "ports": worker_task.target.ports,
                "options": worker_task.options,
            }

            # Import and create task signature
            celery_task = celery_app.signature(
                task_name,
                args=[task_data],
                immutable=True,
                queue=queue_name
            )
            
            celery_tasks.append(celery_task)
        
        # Execute as parallel group
        job = group(celery_tasks)
        result = job.apply_async()
        
        # Extract task IDs
        for task_result in result.results:
            task_ids.append(task_result.id)
            # Update worker task with Celery ID
            for worker_task in scan_job.worker_tasks:
                if not worker_task.celery_task_id:
                    worker_task.celery_task_id = task_result.id
                    worker_task.status = ScanStatus.QUEUED
                    break
        
        return task_ids
    
    def _dispatch_sequential(self, scan_job: ScanJob) -> List[str]:
        """
        Dispatch tasks sequentially
        
        Args:
            scan_job: Scan job
        
        Returns:
            List of Celery task IDs
        """
        from ..services.celery_app import celery_app
        
        task_ids = []
        
        for worker_task in scan_job.worker_tasks:
            task_name = f"{worker_task.worker_type.value}.scan"
            queue_name = worker_task.worker_type.value

            task_data = {
                "scan_id": str(scan_job.id),
                "worker_task_id": str(worker_task.id),
                "target": worker_task.target.value,
                "target_type": worker_task.target.type,
                "ports": worker_task.target.ports,
                "options": worker_task.options,
            }

            # Send task to queue
            result = celery_app.send_task(
                task_name,
                args=[task_data],
                queue=queue_name
            )
            
            task_ids.append(result.id)
            worker_task.celery_task_id = result.id
            worker_task.status = ScanStatus.QUEUED
        
        return task_ids
    
    def cancel_tasks(self, scan_job_id: UUID) -> bool:
        """
        Cancel all tasks for a scan job
        
        Args:
            scan_job_id: Scan job ID
        
        Returns:
            True if cancelled successfully
        """
        from ..services.celery_app import celery_app
        
        task_ids = self.active_tasks.get(scan_job_id, [])
        
        if not task_ids:
            logger.warning(f"No active tasks found for scan {scan_job_id}")
            return True
        
        try:
            # Revoke all tasks
            for task_id in task_ids:
                celery_app.control.revoke(
                    task_id,
                    terminate=True,
                    signal='SIGKILL'
                )
            
            # Remove from active tasks
            del self.active_tasks[scan_job_id]
            
            logger.info(f"Cancelled {len(task_ids)} tasks for scan {scan_job_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to cancel tasks for scan {scan_job_id}: {e}")
            return False
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """
        Get status of a Celery task
        
        Args:
            task_id: Celery task ID
        
        Returns:
            Task status dict or None
        """
        from ..services.celery_app import celery_app
        
        try:
            result = celery_app.AsyncResult(task_id)
            
            return {
                'id': task_id,
                'status': result.status,
                'ready': result.ready(),
                'successful': result.successful() if result.ready() else None,
                'result': result.result if result.ready() else None
            }
        
        except Exception as e:
            logger.error(f"Failed to get status for task {task_id}: {e}")
            return None
    
    def _determine_workers_for_targets(
        self,
        targets: List[ScanTarget]
    ) -> List[WorkerType]:
        """
        Determine which workers to use based on targets
        
        Args:
            targets: List of scan targets
        
        Returns:
            List of worker types
        """
        workers: Set[WorkerType] = set()
        
        for target in targets:
            target_workers = self.TARGET_TYPE_WORKERS.get(target.type, [])
            workers.update(target_workers)
        
        return list(workers)
    
    def _is_worker_suitable(
        self,
        worker_type: WorkerType,
        target: ScanTarget
    ) -> bool:
        """
        Check if worker is suitable for target
        
        Args:
            worker_type: Worker type
            target: Scan target
        
        Returns:
            True if suitable
        """
        suitable_workers = self.TARGET_TYPE_WORKERS.get(target.type, [])
        return worker_type in suitable_workers
    
    def _build_worker_options(
        self,
        worker_type: WorkerType,
        profile: ScanProfile,
        target: ScanTarget
    ) -> Dict:
        """
        Build worker-specific options based on profile
        
        Args:
            worker_type: Worker type
            profile: Scan profile
            target: Scan target
        
        Returns:
            Worker options dict
        """
        options = {
            'profile': profile.value,
            'timeout': settings.WORKER_TIMEOUT_SECONDS,
            'max_retries': settings.WORKER_MAX_RETRIES
        }
        
        # Worker-specific options
        if worker_type == WorkerType.NMAP:
            options.update({
                'scan_type': self._nmap_scan_type_for_profile(profile),
                'ports': target.ports or []
            })
        
        elif worker_type == WorkerType.ZAP:
            options.update({
                'spider_enabled': profile in [ScanProfile.COMPREHENSIVE, ScanProfile.QUICK],
                'active_scan': profile in [ScanProfile.COMPREHENSIVE, ScanProfile.TARGETED],
                'ajax_spider': profile == ScanProfile.COMPREHENSIVE
            })
        
        elif worker_type == WorkerType.TRIVY:
            options.update({
                'scan_type': 'image' if target.type == 'container_image' else 'fs',
                'severity': self._trivy_severity_for_profile(profile)
            })
        
        elif worker_type == WorkerType.PROWLER:
            options.update({
                'service_filter': target.metadata.get('services', []) if target.metadata else []
            })
        
        elif worker_type == WorkerType.METASPLOIT:
            options.update({
                'mode': 'verify' if profile != ScanProfile.COMPREHENSIVE else 'exploit'
            })
        
        return options
    
    def _nmap_scan_type_for_profile(self, profile: ScanProfile) -> str:
        """Map scan profile to Nmap scan type"""
        mapping = {
            ScanProfile.QUICK: 'quick',
            ScanProfile.COMPREHENSIVE: 'comprehensive',
            ScanProfile.STEALTH: 'stealth',
            ScanProfile.TARGETED: 'custom',
            ScanProfile.AI_DRIVEN: 'comprehensive'
        }
        return mapping.get(profile, 'quick')
    
    def _trivy_severity_for_profile(self, profile: ScanProfile) -> List[str]:
        """Map scan profile to Trivy severity levels"""
        if profile == ScanProfile.QUICK:
            return ['CRITICAL', 'HIGH']
        elif profile == ScanProfile.COMPREHENSIVE:
            return ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
        else:
            return ['CRITICAL', 'HIGH', 'MEDIUM']
