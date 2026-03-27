from celery import Celery

celery_app = Celery(
    "nmap_worker",
    broker="amqp://guest:guest@rabbitmq:5672//",
    backend="rpc://"
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)