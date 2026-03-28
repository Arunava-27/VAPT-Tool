"""
Scan workflow state machine

Manages scan lifecycle transitions and validates state changes
"""

from typing import Dict, List, Optional, Set
from datetime import datetime
import logging

from ..models.scan_models import (
    ScanStatus, 
    ScanJob, 
    StateTransition,
    WorkflowEvent
)

logger = logging.getLogger(__name__)


class ScanStateMachine:
    """
    State machine for scan workflow lifecycle
    
    State flow:
    pending → queued → preparing → scanning → analyzing → aggregating → completed
                                      ↓           ↓           ↓
                                   failed     failed      failed
                                      ↓           ↓           ↓
                                   cancelled  cancelled   cancelled
    """
    
    # Define valid state transitions
    VALID_TRANSITIONS: Dict[ScanStatus, Set[ScanStatus]] = {
        ScanStatus.PENDING: {
            ScanStatus.QUEUED,
            ScanStatus.CANCELLED
        },
        ScanStatus.QUEUED: {
            ScanStatus.PREPARING,
            ScanStatus.CANCELLED,
            ScanStatus.FAILED
        },
        ScanStatus.PREPARING: {
            ScanStatus.SCANNING,
            ScanStatus.FAILED,
            ScanStatus.CANCELLED
        },
        ScanStatus.SCANNING: {
            ScanStatus.ANALYZING,
            ScanStatus.FAILED,
            ScanStatus.CANCELLED,
            ScanStatus.TIMEOUT
        },
        ScanStatus.ANALYZING: {
            ScanStatus.AGGREGATING,
            ScanStatus.FAILED,
            ScanStatus.CANCELLED
        },
        ScanStatus.AGGREGATING: {
            ScanStatus.COMPLETED,
            ScanStatus.FAILED,
            ScanStatus.CANCELLED
        },
        ScanStatus.COMPLETED: set(),  # Terminal state
        ScanStatus.FAILED: set(),  # Terminal state
        ScanStatus.CANCELLED: set(),  # Terminal state
        ScanStatus.TIMEOUT: set()  # Terminal state
    }
    
    # Terminal states (no further transitions allowed)
    TERMINAL_STATES = {
        ScanStatus.COMPLETED,
        ScanStatus.FAILED,
        ScanStatus.CANCELLED,
        ScanStatus.TIMEOUT
    }
    
    # Active states (scan is in progress)
    ACTIVE_STATES = {
        ScanStatus.QUEUED,
        ScanStatus.PREPARING,
        ScanStatus.SCANNING,
        ScanStatus.ANALYZING,
        ScanStatus.AGGREGATING
    }
    
    def __init__(self):
        """Initialize state machine"""
        self.transition_history: List[StateTransition] = []
    
    def can_transition(self, from_status: ScanStatus, to_status: ScanStatus) -> bool:
        """
        Check if state transition is valid
        
        Args:
            from_status: Current status
            to_status: Desired status
        
        Returns:
            True if transition is allowed
        """
        if from_status not in self.VALID_TRANSITIONS:
            logger.error(f"Unknown from_status: {from_status}")
            return False
        
        allowed_transitions = self.VALID_TRANSITIONS[from_status]
        return to_status in allowed_transitions
    
    def transition(
        self,
        scan_job: ScanJob,
        to_status: ScanStatus,
        reason: Optional[str] = None
    ) -> bool:
        """
        Transition scan job to new status
        
        Args:
            scan_job: Scan job to transition
            to_status: Target status
            reason: Optional reason for transition
        
        Returns:
            True if transition succeeded
        
        Raises:
            ValueError: If transition is invalid
        """
        from_status = scan_job.status
        
        # Check if already in target state
        if from_status == to_status:
            logger.warning(f"Scan {scan_job.id} already in status {to_status}")
            return True
        
        # Validate transition
        if not self.can_transition(from_status, to_status):
            error_msg = f"Invalid transition: {from_status} → {to_status}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Update scan job status
        scan_job.status = to_status
        
        # Update timing fields
        now = datetime.now()
        
        if to_status == ScanStatus.QUEUED:
            scan_job.queued_at = now
            scan_job.current_phase = "queued"
            scan_job.progress_percentage = 5
        
        elif to_status == ScanStatus.PREPARING:
            scan_job.current_phase = "preparing"
            scan_job.progress_percentage = 10
        
        elif to_status == ScanStatus.SCANNING:
            scan_job.started_at = scan_job.started_at or now
            scan_job.current_phase = "scanning"
            scan_job.progress_percentage = 20
        
        elif to_status == ScanStatus.ANALYZING:
            scan_job.current_phase = "analyzing"
            scan_job.progress_percentage = 70
        
        elif to_status == ScanStatus.AGGREGATING:
            scan_job.current_phase = "aggregating"
            scan_job.progress_percentage = 90
        
        elif to_status in self.TERMINAL_STATES:
            scan_job.completed_at = now
            scan_job.progress_percentage = 100
            scan_job.current_phase = "completed" if to_status == ScanStatus.COMPLETED else "failed"
        
        # Record transition
        transition = StateTransition(
            scan_job_id=scan_job.id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            timestamp=now
        )
        self.transition_history.append(transition)
        
        logger.info(
            f"Scan {scan_job.id} transitioned: {from_status} → {to_status} "
            f"({scan_job.progress_percentage}%)"
        )
        
        return True
    
    def is_terminal(self, status: ScanStatus) -> bool:
        """Check if status is terminal"""
        return status in self.TERMINAL_STATES
    
    def is_active(self, status: ScanStatus) -> bool:
        """Check if status indicates active scanning"""
        return status in self.ACTIVE_STATES
    
    def get_transition_history(self, scan_job_id) -> List[StateTransition]:
        """Get transition history for a scan job"""
        return [
            t for t in self.transition_history
            if t.scan_job_id == scan_job_id
        ]
    
    def calculate_progress(self, scan_job: ScanJob) -> int:
        """
        Calculate scan progress percentage based on state and tasks
        
        Args:
            scan_job: Scan job
        
        Returns:
            Progress percentage (0-100)
        """
        if scan_job.status == ScanStatus.PENDING:
            return 0
        
        if scan_job.status == ScanStatus.QUEUED:
            return 5
        
        if scan_job.status == ScanStatus.PREPARING:
            return 10
        
        if scan_job.status in self.TERMINAL_STATES:
            return 100
        
        # For scanning/analyzing states, calculate based on task progress
        if scan_job.worker_tasks:
            total_tasks = len(scan_job.worker_tasks)
            completed_tasks = sum(
                1 for task in scan_job.worker_tasks
                if task.status in [ScanStatus.COMPLETED, ScanStatus.FAILED]
            )
            
            # Scanning phase: 20-70%
            if scan_job.status == ScanStatus.SCANNING:
                task_progress = (completed_tasks / total_tasks) * 50
                return int(20 + task_progress)
            
            # Analyzing phase: 70-90%
            elif scan_job.status == ScanStatus.ANALYZING:
                return 70 + min(int((completed_tasks / total_tasks) * 20), 20)
            
            # Aggregating phase: 90-95%
            elif scan_job.status == ScanStatus.AGGREGATING:
                return 90
        
        return scan_job.progress_percentage
    
    def reset(self):
        """Reset state machine (clear history)"""
        self.transition_history.clear()


class WorkflowEngine:
    """
    High-level workflow engine that orchestrates scan execution
    """
    
    def __init__(self):
        """Initialize workflow engine"""
        self.state_machine = ScanStateMachine()
        self.events: List[WorkflowEvent] = []
    
    def start_scan(self, scan_job: ScanJob) -> bool:
        """
        Start scan execution workflow
        
        Args:
            scan_job: Scan job to start
        
        Returns:
            True if started successfully
        """
        try:
            # Transition to queued
            self.state_machine.transition(
                scan_job,
                ScanStatus.QUEUED,
                reason="Scan initiated by user"
            )
            
            self._emit_event(
                "scan_started",
                scan_job.id,
                f"Scan {scan_job.name} started"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to start scan {scan_job.id}: {e}")
            scan_job.error = str(e)
            self.state_machine.transition(
                scan_job,
                ScanStatus.FAILED,
                reason=f"Startup failed: {e}"
            )
            return False
    
    def prepare_scan(self, scan_job: ScanJob) -> bool:
        """
        Prepare scan environment
        
        Args:
            scan_job: Scan job
        
        Returns:
            True if preparation succeeded
        """
        try:
            self.state_machine.transition(
                scan_job,
                ScanStatus.PREPARING,
                reason="Preparing scan environment"
            )
            
            self._emit_event(
                "scan_preparing",
                scan_job.id,
                "Preparing scan environment and worker tasks"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to prepare scan {scan_job.id}: {e}")
            scan_job.error = str(e)
            self.state_machine.transition(
                scan_job,
                ScanStatus.FAILED,
                reason=f"Preparation failed: {e}"
            )
            return False
    
    def start_scanning(self, scan_job: ScanJob) -> bool:
        """
        Begin scanning phase
        
        Args:
            scan_job: Scan job
        
        Returns:
            True if scanning started
        """
        try:
            self.state_machine.transition(
                scan_job,
                ScanStatus.SCANNING,
                reason="Beginning scan execution"
            )
            
            self._emit_event(
                "scanning_started",
                scan_job.id,
                f"Executing {len(scan_job.worker_tasks)} worker tasks"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to start scanning {scan_job.id}: {e}")
            scan_job.error = str(e)
            self.state_machine.transition(
                scan_job,
                ScanStatus.FAILED,
                reason=f"Scan start failed: {e}"
            )
            return False
    
    def complete_scan(self, scan_job: ScanJob) -> bool:
        """
        Complete scan successfully
        
        Args:
            scan_job: Scan job
        
        Returns:
            True if completed
        """
        try:
            # Update progress through intermediate states
            if scan_job.status == ScanStatus.SCANNING:
                self.state_machine.transition(
                    scan_job,
                    ScanStatus.ANALYZING,
                    reason="Scanning complete, analyzing results"
                )
            
            if scan_job.status == ScanStatus.ANALYZING:
                self.state_machine.transition(
                    scan_job,
                    ScanStatus.AGGREGATING,
                    reason="Analysis complete, aggregating results"
                )
            
            if scan_job.status == ScanStatus.AGGREGATING:
                self.state_machine.transition(
                    scan_job,
                    ScanStatus.COMPLETED,
                    reason="Scan completed successfully"
                )
            
            self._emit_event(
                "scan_completed",
                scan_job.id,
                f"Scan completed with {scan_job.vulnerabilities_found} vulnerabilities"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to complete scan {scan_job.id}: {e}")
            scan_job.error = str(e)
            self.state_machine.transition(
                scan_job,
                ScanStatus.FAILED,
                reason=f"Completion failed: {e}"
            )
            return False
    
    def fail_scan(self, scan_job: ScanJob, error: str) -> bool:
        """
        Mark scan as failed
        
        Args:
            scan_job: Scan job
            error: Error message
        
        Returns:
            True if marked failed
        """
        try:
            scan_job.error = error
            self.state_machine.transition(
                scan_job,
                ScanStatus.FAILED,
                reason=error
            )
            
            self._emit_event(
                "scan_failed",
                scan_job.id,
                f"Scan failed: {error}"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to mark scan {scan_job.id} as failed: {e}")
            return False
    
    def cancel_scan(self, scan_job: ScanJob, reason: Optional[str] = None) -> bool:
        """
        Cancel scan execution
        
        Args:
            scan_job: Scan job
            reason: Optional cancellation reason
        
        Returns:
            True if cancelled
        """
        try:
            self.state_machine.transition(
                scan_job,
                ScanStatus.CANCELLED,
                reason=reason or "Cancelled by user"
            )
            
            self._emit_event(
                "scan_cancelled",
                scan_job.id,
                reason or "Scan cancelled by user"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to cancel scan {scan_job.id}: {e}")
            return False
    
    def _emit_event(self, event_type: str, scan_job_id, message: str):
        """Emit workflow event"""
        event = WorkflowEvent(
            event_type=event_type,
            scan_job_id=scan_job_id,
            message=message
        )
        self.events.append(event)
        logger.info(f"Event: {event_type} - {message}")
    
    def get_events(self, scan_job_id) -> List[WorkflowEvent]:
        """Get events for a scan job"""
        return [e for e in self.events if e.scan_job_id == scan_job_id]
