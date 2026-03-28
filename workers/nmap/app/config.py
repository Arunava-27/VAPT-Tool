import os
from celery import Celery

_broker = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//")

celery_app = Celery(
    "nmap_worker",
    broker=_broker,
    backend="rpc://"
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)