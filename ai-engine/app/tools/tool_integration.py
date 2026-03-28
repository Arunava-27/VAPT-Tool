"""
Tool integration layer — AI agents use this to trigger Celery worker tasks
and retrieve results.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from celery import Celery

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)

_celery = Celery(broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_RESULT_BACKEND)


class ToolIntegration:
    """
    Sends tasks to security tool workers and polls for results.
    Maps tool name → Celery task name.
    """

    TOOL_TASKS = {
        "nmap":       "nmap.scan",
        "zap":        "zap.scan",
        "trivy":      "trivy.scan",
        "prowler":    "prowler.scan",
        "metasploit": "metasploit.scan",
    }

    def dispatch(
        self,
        tool: str,
        target: str,
        options: Optional[Dict[str, Any]] = None,
        scan_id: Optional[str] = None,
    ) -> str:
        """Dispatch a tool task. Returns the Celery task ID."""
        task_name = self.TOOL_TASKS.get(tool)
        if not task_name:
            raise ValueError(f"Unknown tool: {tool}. Available: {list(self.TOOL_TASKS.keys())}")

        task_data = {
            "scan_id": scan_id or "",
            "target": target,
            "options": options or {},
        }
        result = _celery.send_task(task_name, args=[task_data])
        logger.info(f"[Tools] Dispatched {tool} task {result.id} for target {target}")
        return result.id

    def wait_for_result(
        self,
        task_id: str,
        timeout_seconds: int = 300,
        poll_interval: int = 5,
    ) -> Dict[str, Any]:
        """Poll until the task completes or times out."""
        result = _celery.AsyncResult(task_id)
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            if result.ready():
                if result.successful():
                    return result.get()
                else:
                    raise RuntimeError(f"Task {task_id} failed: {result.result}")
            time.sleep(poll_interval)

        raise TimeoutError(f"Task {task_id} did not complete within {timeout_seconds}s")

    def dispatch_and_wait(
        self,
        tool: str,
        target: str,
        options: Optional[Dict[str, Any]] = None,
        scan_id: Optional[str] = None,
        timeout_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Convenience: dispatch and block until done."""
        task_id = self.dispatch(tool, target, options, scan_id)
        return self.wait_for_result(task_id, timeout_seconds)


# Singleton
tool_integration = ToolIntegration()
