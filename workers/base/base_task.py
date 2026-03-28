import json
import logging
import os
import time
import signal
import concurrent.futures
from typing import Any, Dict, Optional, Callable
from functools import wraps
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categorize errors for better handling and reporting"""
    TIMEOUT = "timeout"
    NETWORK = "network"
    INVALID_INPUT = "invalid_input"
    TOOL_ERROR = "tool_error"
    PERMISSION_DENIED = "permission_denied"
    RESOURCE_ERROR = "resource_error"
    UNKNOWN = "unknown"


class TaskError(Exception):
    """Base exception for task errors with categorization"""
    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.UNKNOWN, 
                 original_error: Optional[Exception] = None):
        self.message = message
        self.category = category
        self.original_error = original_error
        super().__init__(self.message)


class BaseTask:
    """
    Enhanced base class for all security tool workers.
    
    Features:
    - Automatic retry logic with exponential backoff
    - Timeout handling
    - Graceful shutdown support
    - Result validation
    - Error categorization
    - Comprehensive logging
    """
    
    # Default configuration (can be overridden in subclasses)
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # seconds
    DEFAULT_TIMEOUT = 600  # 10 minutes
    SHUTDOWN_GRACE_PERIOD = 30  # seconds
    
    def __init__(self):
        self._shutdown_requested = False
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Setup handlers for graceful shutdown"""
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.warning(f"Shutdown signal received: {signum}")
        self._shutdown_requested = True
    
    def should_shutdown(self) -> bool:
        """Check if shutdown has been requested"""
        return self._shutdown_requested

    # =========================================================================
    # Database Write-back (BUG-01)
    # =========================================================================

    def _get_db_session(self):
        """Create a SQLAlchemy session using DATABASE_URL env var"""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.warning("DATABASE_URL not set — scan status updates disabled")
            return None
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            engine = create_engine(database_url)
            Session = sessionmaker(bind=engine)
            return Session()
        except Exception as exc:
            logger.error(f"Failed to create DB session: {exc}")
            return None

    def update_scan_status(
        self,
        scan_id: str,
        status: str,
        result_summary: Optional[Dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Write scan status back to the database.

        Called by workers to reflect running / completed / failed state.
        """
        from datetime import datetime
        from sqlalchemy import text

        session = self._get_db_session()
        if not session:
            return
        try:
            now = datetime.utcnow()
            if status == "running":
                session.execute(
                    text(
                        "UPDATE scans SET status = :status, started_at = :started_at,"
                        " updated_at = :updated_at WHERE id = :scan_id"
                    ),
                    {"status": status, "started_at": now, "updated_at": now, "scan_id": scan_id},
                )
            elif status == "completed":
                session.execute(
                    text(
                        "UPDATE scans SET status = :status,"
                        " result_summary = CAST(:result_summary AS JSONB),"
                        " completed_at = :completed_at, updated_at = :updated_at"
                        " WHERE id = :scan_id"
                    ),
                    {
                        "status": status,
                        "result_summary": json.dumps(result_summary or {}),
                        "completed_at": now,
                        "updated_at": now,
                        "scan_id": scan_id,
                    },
                )
            elif status == "failed":
                session.execute(
                    text(
                        "UPDATE scans SET status = :status, error = :error,"
                        " completed_at = :completed_at, updated_at = :updated_at"
                        " WHERE id = :scan_id"
                    ),
                    {
                        "status": status,
                        "error": error or "",
                        "completed_at": now,
                        "updated_at": now,
                        "scan_id": scan_id,
                    },
                )
            session.commit()
            logger.info(f"Updated scan {scan_id} status → {status}")
        except Exception as exc:
            logger.error(f"Failed to update scan {scan_id} status: {exc}")
            session.rollback()
        finally:
            session.close()
    
    # =========================================================================
    # Logging Methods
    # =========================================================================
    
    def log_start(self, task_id: str, target: str, tool: str = ""):
        """Log task start with details"""
        tool_str = f"[{tool}] " if tool else ""
        logger.info(f"{tool_str}[{task_id}] Starting scan for target: {target}")
    
    def log_success(self, task_id: str, duration: float = 0, tool: str = ""):
        """Log successful task completion"""
        tool_str = f"[{tool}] " if tool else ""
        duration_str = f" (Duration: {duration:.2f}s)" if duration else ""
        logger.info(f"{tool_str}[{task_id}] Task completed successfully{duration_str}")
    
    def log_error(self, task_id: str, error: Exception, category: ErrorCategory = ErrorCategory.UNKNOWN, tool: str = ""):
        """Log error with categorization"""
        tool_str = f"[{tool}] " if tool else ""
        logger.error(f"{tool_str}[{task_id}] Error ({category.value}): {str(error)}")
    
    def log_retry(self, task_id: str, attempt: int, max_retries: int, error: str, tool: str = ""):
        """Log retry attempt"""
        tool_str = f"[{tool}] " if tool else ""
        logger.warning(f"{tool_str}[{task_id}] Retry {attempt}/{max_retries} after error: {error}")
    
    def log_progress(self, task_id: str, message: str, tool: str = ""):
        """Log progress update"""
        tool_str = f"[{tool}] " if tool else ""
        logger.info(f"{tool_str}[{task_id}] Progress: {message}")
    
    # =========================================================================
    # Retry Logic
    # =========================================================================
    
    def with_retry(self, func: Callable, *args, max_retries: Optional[int] = None, 
                   task_id: str = "", tool: str = "", **kwargs) -> Any:
        """
        Execute function with retry logic and exponential backoff
        
        Args:
            func: Function to execute
            max_retries: Maximum retry attempts (default: self.MAX_RETRIES)
            task_id: Task ID for logging
            tool: Tool name for logging
            *args, **kwargs: Arguments to pass to func
        
        Returns:
            Function result
        
        Raises:
            TaskError: If all retries exhausted
        """
        max_retries = max_retries or self.MAX_RETRIES
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                if self.should_shutdown():
                    raise TaskError("Task cancelled due to shutdown", ErrorCategory.UNKNOWN)
                
                return func(*args, **kwargs)
            
            except Exception as e:
                last_error = e
                category = self.categorize_error(e)
                
                if attempt < max_retries and self.is_retriable(category):
                    delay = self.RETRY_DELAY * (2 ** (attempt - 1))  # Exponential backoff
                    self.log_retry(task_id, attempt, max_retries, str(e), tool)
                    time.sleep(delay)
                else:
                    break
        
        # All retries exhausted
        category = self.categorize_error(last_error)
        raise TaskError(
            f"Task failed after {max_retries} attempts: {str(last_error)}",
            category=category,
            original_error=last_error
        )
    
    # =========================================================================
    # Error Handling
    # =========================================================================
    
    def categorize_error(self, error: Exception) -> ErrorCategory:
        """
        Categorize error for better handling
        
        Args:
            error: Exception to categorize
        
        Returns:
            ErrorCategory enum value
        """
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # Timeout errors
        if 'timeout' in error_str or 'timed out' in error_str:
            return ErrorCategory.TIMEOUT
        
        # Network errors
        if any(x in error_str for x in ['connection', 'network', 'unreachable', 'dns', 'resolve']):
            return ErrorCategory.NETWORK
        
        # Permission errors
        if any(x in error_str for x in ['permission', 'denied', 'forbidden', 'unauthorized']):
            return ErrorCategory.PERMISSION_DENIED
        
        # Resource errors
        if any(x in error_str for x in ['memory', 'disk', 'resource', 'space']):
            return ErrorCategory.RESOURCE_ERROR
        
        # Input validation errors
        if 'invalid' in error_str or 'valueerror' in error_type:
            return ErrorCategory.INVALID_INPUT
        
        # Tool-specific errors
        if any(x in error_str for x in ['nmap', 'zap', 'trivy', 'prowler', 'metasploit']):
            return ErrorCategory.TOOL_ERROR
        
        return ErrorCategory.UNKNOWN
    
    def is_retriable(self, category: ErrorCategory) -> bool:
        """
        Determine if error category is retriable
        
        Args:
            category: Error category
        
        Returns:
            True if error should be retried
        """
        # Don't retry these categories
        non_retriable = {
            ErrorCategory.INVALID_INPUT,
            ErrorCategory.PERMISSION_DENIED,
        }
        return category not in non_retriable
    
    # =========================================================================
    # Result Validation
    # =========================================================================
    
    def validate_result(self, result: Dict[str, Any], required_fields: list = None) -> bool:
        """
        Validate task result structure
        
        Args:
            result: Result dictionary to validate
            required_fields: List of required field names
        
        Returns:
            True if valid, False otherwise
        """
        if not isinstance(result, dict):
            logger.error("Result is not a dictionary")
            return False
        
        # Default required fields
        default_required = ['status', 'task_id', 'tool', 'target']
        required_fields = required_fields or default_required
        
        # Check required fields
        missing_fields = [field for field in required_fields if field not in result]
        if missing_fields:
            logger.error(f"Missing required fields in result: {missing_fields}")
            return False
        
        # Validate status field
        valid_statuses = ['completed', 'failed', 'partial', 'timeout']
        if result.get('status') not in valid_statuses:
            logger.error(f"Invalid status: {result.get('status')}")
            return False
        
        return True
    
    def create_result(self, status: str, task_id: str, tool: str, target: str,
                     result_data: Any = None, error: Optional[str] = None,
                     metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Create standardized result dictionary
        
        Args:
            status: Task status (completed, failed, partial, timeout)
            task_id: Celery task ID
            tool: Tool name (nmap, zap, etc.)
            target: Scan target
            result_data: Actual scan results
            error: Error message if failed
            metadata: Additional metadata
        
        Returns:
            Standardized result dictionary
        """
        result = {
            'status': status,
            'task_id': task_id,
            'tool': tool,
            'target': target,
            'result': result_data,
            'error': error,
            'timestamp': time.time(),
        }
        
        if metadata:
            result['metadata'] = metadata
        
        return result
    
    # =========================================================================
    # Timeout Handling
    # =========================================================================
    
    def with_timeout(self, func: Callable, timeout: Optional[int] = None,
                     task_id: str = "", tool: str = "", *args, **kwargs) -> Any:
        """
        Execute function with actual timeout enforcement via ThreadPoolExecutor.

        Args:
            func: Function to execute
            timeout: Timeout in seconds (default: self.DEFAULT_TIMEOUT)
            task_id: Task ID for logging
            tool: Tool name for logging
            *args, **kwargs: Arguments to pass to func

        Returns:
            Function result

        Raises:
            TaskError: If timeout exceeded
        """
        timeout = timeout or self.DEFAULT_TIMEOUT

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                tool_str = f"[{tool}] " if tool else ""
                logger.error(
                    f"{tool_str}[{task_id}] Task timed out after {timeout}s"
                )
                raise TaskError(
                    f"Task exceeded timeout of {timeout}s",
                    category=ErrorCategory.TIMEOUT,
                )