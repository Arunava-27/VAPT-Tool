from celery import Celery

app = Celery(
    "test_client",
    broker="amqp://guest:guest@localhost:5672//",
    backend="rpc://"
)

result = app.send_task(
    "nmap.scan",
    args=[{"target": "scanme.nmap.org"}],
    ignore_result=False
)

print("Task ID:", result.id)

output = result.get(timeout=120)
print("Result:", output)