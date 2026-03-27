import logging

logger = logging.getLogger(__name__)

class BaseTask:
    def log_start(self, task_id, target):
        logger.info(f"[{task_id}] Starting scan for {target}")

    def log_success(self, task_id):
        logger.info(f"[{task_id}] Task completed successfully")

    def log_error(self, task_id, error):
        logger.error(f"[{task_id}] Error: {error}")