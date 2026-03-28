"""
Infrastructure services health check endpoint.
Probes all platform dependencies: DB, Redis, RabbitMQ, Elasticsearch, MinIO,
Celery workers, and the AI engine.
"""

import asyncio
import time
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from ....db.session import get_db
from ....core.config import settings
from .auth import get_current_active_user
from ....models.user import User

router = APIRouter()

# ---------------------------------------------------------------------------
# Individual probes
# ---------------------------------------------------------------------------

async def probe_postgres(db: Session) -> Dict[str, Any]:
    t = time.monotonic()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "latency_ms": round((time.monotonic() - t) * 1000, 1)}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def probe_redis() -> Dict[str, Any]:
    t = time.monotonic()
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        r.ping()
        info = r.info("memory")
        return {
            "status": "healthy",
            "latency_ms": round((time.monotonic() - t) * 1000, 1),
            "used_memory": info.get("used_memory_human", "?"),
        }
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def probe_rabbitmq() -> Dict[str, Any]:
    t = time.monotonic()
    try:
        import aio_pika
        conn = await asyncio.wait_for(
            aio_pika.connect_robust(settings.RABBITMQ_URL), timeout=5
        )
        await conn.close()
        return {"status": "healthy", "latency_ms": round((time.monotonic() - t) * 1000, 1)}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def probe_elasticsearch() -> Dict[str, Any]:
    t = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(f"{settings.ELASTICSEARCH_URL}/_cluster/health")
            data = res.json()
            return {
                "status": "healthy" if data.get("status") in ("green", "yellow") else "unhealthy",
                "latency_ms": round((time.monotonic() - t) * 1000, 1),
                "cluster_status": data.get("status", "?"),
                "nodes": data.get("number_of_nodes", "?"),
            }
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def probe_minio() -> Dict[str, Any]:
    t = time.monotonic()
    try:
        scheme = "https" if settings.MINIO_SECURE else "http"
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(f"{scheme}://{settings.MINIO_ENDPOINT}/minio/health/live")
            return {
                "status": "healthy" if res.status_code == 200 else "unhealthy",
                "latency_ms": round((time.monotonic() - t) * 1000, 1),
            }
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def probe_ai_engine() -> Dict[str, Any]:
    t = time.monotonic()
    try:
        ai_url = getattr(settings, "AI_ENGINE_URL", "http://ai-engine:8001")
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(f"{ai_url}/health")
            data = res.json()
            return {
                "status": "healthy" if res.status_code == 200 else "unhealthy",
                "latency_ms": round((time.monotonic() - t) * 1000, 1),
                "detail": data,
            }
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def probe_celery_workers() -> List[Dict[str, Any]]:
    """Inspect all Celery workers via broker ping."""
    try:
        from celery import Celery
        import os

        broker = os.getenv("CELERY_BROKER_URL", settings.CELERY_BROKER_URL)
        app = Celery(broker=broker, backend="rpc://")

        # Run synchronously in thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()

        def _inspect():
            insp = app.control.inspect(timeout=3)
            pong = insp.ping() or {}
            stats = insp.stats() or {}
            return pong, stats

        pong, stats = await loop.run_in_executor(None, _inspect)

        workers = []
        for hostname in pong:
            wstats = stats.get(hostname, {})
            pool = wstats.get("pool", {})
            workers.append({
                "name": hostname,
                "status": "healthy",
                "concurrency": pool.get("max-concurrency", "?"),
                "processes": pool.get("processes", []),
                "tasks_processed": wstats.get("total", {}),
            })

        # Add known workers that didn't respond
        known = ["nmap", "zap", "trivy", "prowler", "metasploit"]
        responding = {w["name"] for w in workers}
        for k in known:
            if not any(k in n for n in responding):
                workers.append({"name": f"worker-{k}", "status": "unreachable", "concurrency": "?"})

        return sorted(workers, key=lambda w: w["name"])
    except Exception as exc:
        return [{"name": "celery", "status": "unhealthy", "error": str(exc)}]


# ---------------------------------------------------------------------------
# Aggregated endpoint
# ---------------------------------------------------------------------------

@router.get("/services")
async def services_health(
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Full infrastructure health check.
    Probes all platform services in parallel and returns a consolidated report.
    """
    t_start = time.monotonic()

    (
        pg_result,
        redis_result,
        rmq_result,
        es_result,
        minio_result,
        ai_result,
        workers_result,
    ) = await asyncio.gather(
        probe_postgres(db),
        probe_redis(),
        probe_rabbitmq(),
        probe_elasticsearch(),
        probe_minio(),
        probe_ai_engine(),
        probe_celery_workers(),
        return_exceptions=False,
    )

    services = [
        {"id": "postgres",       "name": "PostgreSQL",      "category": "database", **pg_result},
        {"id": "redis",          "name": "Redis",            "category": "cache",    **redis_result},
        {"id": "rabbitmq",       "name": "RabbitMQ",         "category": "queue",    **rmq_result},
        {"id": "elasticsearch",  "name": "Elasticsearch",    "category": "search",   **es_result},
        {"id": "minio",          "name": "MinIO",            "category": "storage",  **minio_result},
        {"id": "ai-engine",      "name": "AI Engine",        "category": "backend",  **ai_result},
    ]

    for w in workers_result:
        services.append({
            "id": w["name"],
            "name": w["name"].replace("celery@", "").split("-")[0].upper() + " Worker",
            "category": "worker",
            **{k: v for k, v in w.items() if k != "name"},
        })

    healthy = sum(1 for s in services if s["status"] == "healthy")
    total = len(services)
    overall = "healthy" if healthy == total else ("degraded" if healthy > 0 else "unhealthy")

    return {
        "overall": overall,
        "healthy": healthy,
        "total": total,
        "duration_ms": round((time.monotonic() - t_start) * 1000, 1),
        "services": services,
    }
