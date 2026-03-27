import logging
from .config import celery_app
from .scanner import run_nmap_scan
from .parser import parse_nmap_xml

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@celery_app.task(name="nmap.scan", bind=True)
def nmap_scan(self, task_data):
    try:
        target = task_data.get("target")

        if not target:
            raise ValueError("Target is required")

        logger.info(f"[{self.request.id}] Starting scan for target: {target}")

        # Step 1: Run scan
        xml_output = run_nmap_scan(target)
        logger.info(f"[{self.request.id}] Scan completed")

        # Step 2: Parse result
        parsed = parse_nmap_xml(xml_output)
        logger.info(f"[{self.request.id}] Parsing completed")

        result = {
            "status": "completed",
            "task_id": self.request.id,
            "target": target,
            "result": parsed
        }

        logger.info(f"[{self.request.id}] Task finished successfully")

        return result

    except Exception as e:
        logger.error(f"[{self.request.id}] Scan failed: {str(e)}")

        return {
            "status": "failed",
            "task_id": self.request.id,
            "error": str(e)
        }