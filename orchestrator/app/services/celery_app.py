"""
Celery application for orchestrator
"""

from celery import Celery
from ..core.config import settings

# Create Celery app
celery_app = Celery(
    'vapt-orchestrator',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.SCAN_TIMEOUT_SECONDS,
    task_soft_time_limit=settings.SCAN_TIMEOUT_SECONDS - 300,  # 5 min before hard limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    result_expires=3600,  # 1 hour
)

# Task routing (if needed for specific queues)
celery_app.conf.task_routes = {
    'nmap.*': {'queue': 'nmap'},
    'zap.*': {'queue': 'zap'},
    'trivy.*': {'queue': 'trivy'},
    'prowler.*': {'queue': 'prowler'},
    'metasploit.*': {'queue': 'metasploit'},
}
