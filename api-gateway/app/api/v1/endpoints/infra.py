"""
Infrastructure services health check endpoint.
Probes all platform dependencies: DB, Redis, RabbitMQ, Elasticsearch, MinIO,
Celery workers, AI engine, and Vault.
"""

import asyncio
import re
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from ....db.session import get_db
from ....core.config import settings
from .auth import get_current_active_user
from ....models.user import User

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rmq_creds():
    """Parse RabbitMQ user/pass/host from the broker URL."""
    rmq_url = getattr(settings, "RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
    m = re.match(r"amqp://([^:]+):([^@]+)@([^:/]+)", rmq_url)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return "guest", "guest", "rabbitmq"

# ---------------------------------------------------------------------------
# Individual probes
# ---------------------------------------------------------------------------

async def probe_postgres(db: Session) -> Dict[str, Any]:
    t = time.monotonic()
    try:
        await asyncio.to_thread(db.execute, text("SELECT 1"))
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
            res = await client.get(f"{ai_url}/info")
            data = res.json() if res.status_code == 200 else {}
            return {
                "status": "healthy" if res.status_code == 200 else "unhealthy",
                "latency_ms": round((time.monotonic() - t) * 1000, 1),
                "active_model": data.get("active_model"),
                "active_provider": data.get("active_provider"),
                "description": f"{data.get('active_provider', 'AI')} · {data.get('active_model', '—')}",
            }
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def probe_celery_workers() -> List[Dict[str, Any]]:
    """Check worker health via RabbitMQ Management API queue consumer counts."""
    known_queues = ["nmap", "zap", "trivy", "prowler", "metasploit"]
    results = []

    try:
        user, password, host = _rmq_creds()
        mgmt_url = f"http://{host}:15672/api/queues/%2F"
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(mgmt_url, auth=(user, password))
            queues = {q["name"]: q for q in res.json()} if res.status_code == 200 else {}

        for name in known_queues:
            q = queues.get(name)
            if q is None:
                results.append({
                    "name": f"worker-{name}",
                    "status": "unreachable",
                    "error": "Queue not found in RabbitMQ",
                })
            else:
                consumers = q.get("consumers", 0)
                messages = q.get("messages", 0)
                results.append({
                    "name": f"worker-{name}",
                    "status": "healthy" if consumers > 0 else "unhealthy",
                    "concurrency": consumers,
                    "tasks_processed": {"queued": messages},
                    **({"error": "No consumers — worker may be down"} if consumers == 0 else {}),
                })
    except Exception as exc:
        for name in known_queues:
            results.append({"name": f"worker-{name}", "status": "unreachable", "error": str(exc)})

    return results


async def probe_vault() -> Dict[str, Any]:
    t = time.monotonic()
    try:
        vault_url = getattr(settings, "VAULT_URL", "http://vault:8200")
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(f"{vault_url}/v1/sys/health")
            data = res.json() if res.status_code in (200, 429, 472, 473, 501, 503) else {}
            initialized = data.get("initialized", False)
            sealed = data.get("sealed", True)
            version = data.get("version", "—")
            if initialized and not sealed:
                status = "healthy"
                description = f"Vault {version} · unsealed"
            elif initialized and sealed:
                status = "degraded"
                description = f"Vault {version} · sealed"
            else:
                status = "unhealthy"
                description = "Vault not initialized"
            return {
                "status": status,
                "latency_ms": round((time.monotonic() - t) * 1000, 1),
                "description": description,
                "vault_version": version,
                "initialized": initialized,
                "sealed": sealed,
            }
    except Exception as exc:
        return {"status": "unreachable", "error": str(exc)}


# Human-readable names and descriptions for each security worker
_WORKER_META: Dict[str, Dict[str, str]] = {
    "nmap":       {"label": "Nmap Scanner",       "description": "Network port & service discovery"},
    "zap":        {"label": "OWASP ZAP",          "description": "Web application vulnerability scanner"},
    "trivy":      {"label": "Trivy",               "description": "Container & image vulnerability scanner"},
    "prowler":    {"label": "Prowler",             "description": "Cloud security posture assessment"},
    "metasploit": {"label": "Metasploit",          "description": "Exploitation framework & testing"},
}


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
        vault_result,
        workers_result,
    ) = await asyncio.gather(
        probe_postgres(db),
        probe_redis(),
        probe_rabbitmq(),
        probe_elasticsearch(),
        probe_minio(),
        probe_ai_engine(),
        probe_vault(),
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
        {"id": "vault",          "name": "HashiCorp Vault",  "category": "secrets",  **vault_result},
    ]

    for w in workers_result:
        queue_name = w["name"].replace("worker-", "")
        display = _WORKER_META.get(queue_name, {
            "label": queue_name.upper() + " Worker",
            "description": f"{queue_name} security scanner",
        })
        services.append({
            "id": w["name"],
            "name": display["label"],
            "description": display["description"],
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


# ---------------------------------------------------------------------------
# Per-service detail
# ---------------------------------------------------------------------------

async def _detail_postgres(db: Session) -> Dict[str, Any]:
    try:
        rows = {}
        for q, key in [
            ("SELECT version()", "version"),
            ("SELECT pg_size_pretty(pg_database_size(current_database()))", "database_size"),
            ("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'", "active_connections"),
            ("SELECT setting::int FROM pg_settings WHERE name='max_connections'", "max_connections"),
            ("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'", "tables"),
        ]:
            result = db.execute(text(q)).scalar()
            rows[key] = result
        return {
            **rows,
            "actions": [
                {"id": "analyze", "label": "Run VACUUM ANALYZE", "variant": "info",    "confirm": False},
                {"id": "test",    "label": "Test Connection",     "variant": "default", "confirm": False},
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "actions": []}


async def _detail_redis() -> Dict[str, Any]:
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=3, decode_responses=True)
        info = r.info()
        keyspace = r.info("keyspace")
        return {
            "version":          info.get("redis_version"),
            "uptime_days":      info.get("uptime_in_days"),
            "connected_clients": info.get("connected_clients"),
            "used_memory":      info.get("used_memory_human"),
            "maxmemory":        info.get("maxmemory_human", "unlimited"),
            "hit_ratio":        round(
                info.get("keyspace_hits", 0) /
                max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 1), 1) * 100, 1
            ),
            "total_commands":   info.get("total_commands_processed"),
            "keyspace":         {k: v for k, v in keyspace.items()},
            "actions": [
                {"id": "ping",      "label": "Ping Redis",        "variant": "default", "confirm": False},
                {"id": "flush_db",  "label": "Flush Cache (DB 0)", "variant": "danger",  "confirm": True,
                 "confirm_message": "This will delete ALL cached data. Are you sure?"},
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "actions": []}


async def _detail_rabbitmq() -> Dict[str, Any]:
    try:
        user, password, host = _rmq_creds()
        async with httpx.AsyncClient(timeout=5) as client:
            overview = (await client.get(f"http://{host}:15672/api/overview", auth=(user, password))).json()
            queues_raw = (await client.get(f"http://{host}:15672/api/queues/%2F", auth=(user, password))).json()

        queues = [
            {
                "name":       q.get("name"),
                "messages":   q.get("messages", 0),
                "consumers":  q.get("consumers", 0),
                "state":      q.get("state", "unknown"),
                "memory":     q.get("memory", 0),
            }
            for q in queues_raw
            if not q.get("name", "").startswith("celery@") and not q.get("name", "").startswith("celeryev")
        ]
        return {
            "version":           overview.get("rabbitmq_version"),
            "erlang_version":    overview.get("erlang_version"),
            "total_connections": overview.get("object_totals", {}).get("connections", 0),
            "total_channels":    overview.get("object_totals", {}).get("channels", 0),
            "messages_ready":    overview.get("queue_totals", {}).get("messages_ready", 0),
            "messages_unacked":  overview.get("queue_totals", {}).get("messages_unacknowledged", 0),
            "queues":            sorted(queues, key=lambda q: q["name"]),
            "actions": [
                {"id": "purge_all", "label": "Purge All Tool Queues", "variant": "danger", "confirm": True,
                 "confirm_message": "This will delete all pending messages from nmap/zap/trivy/prowler/metasploit queues."},
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "actions": []}


async def _detail_elasticsearch() -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            health = (await client.get(f"{settings.ELASTICSEARCH_URL}/_cluster/health")).json()
            stats  = (await client.get(f"{settings.ELASTICSEARCH_URL}/_cluster/stats")).json()
            indices_raw = (await client.get(f"{settings.ELASTICSEARCH_URL}/_cat/indices?format=json&bytes=b")).json()

        indices = [
            {
                "name":   i.get("index"),
                "docs":   int(i.get("docs.count", 0) or 0),
                "size":   int(i.get("store.size", 0) or 0),
                "status": i.get("health", "unknown"),
            }
            for i in indices_raw
            if not i.get("index", "").startswith(".")
        ]
        return {
            "version":       stats.get("nodes", {}).get("versions", ["?"])[0],
            "cluster_name":  health.get("cluster_name"),
            "status":        health.get("status"),
            "nodes":         health.get("number_of_nodes"),
            "data_nodes":    health.get("number_of_data_nodes"),
            "active_shards": health.get("active_shards"),
            "indices":       sorted(indices, key=lambda i: i["name"]),
            "actions": [
                {"id": "refresh",   "label": "Refresh All Indices", "variant": "info",    "confirm": False},
                {"id": "test",      "label": "Test Connection",      "variant": "default", "confirm": False},
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "actions": []}


async def _detail_minio() -> Dict[str, Any]:
    try:
        from minio import Minio
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        buckets = client.list_buckets()
        bucket_data = []
        for b in buckets:
            try:
                size = sum(obj.size for obj in client.list_objects(b.name, recursive=True) if obj.size)
                count = sum(1 for _ in client.list_objects(b.name, recursive=True))
                bucket_data.append({"name": b.name, "objects": count, "size_bytes": size,
                                    "created": str(b.creation_date)})
            except Exception:
                bucket_data.append({"name": b.name, "objects": "?", "size_bytes": 0})
        return {
            "endpoint":   settings.MINIO_ENDPOINT,
            "secure":     settings.MINIO_SECURE,
            "buckets":    bucket_data,
            "actions": [
                {"id": "test", "label": "Test Connection", "variant": "default", "confirm": False},
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "actions": []}


async def _detail_ai_engine() -> Dict[str, Any]:
    try:
        ai_url = getattr(settings, "AI_ENGINE_URL", "http://ai-engine:8001")
        async with httpx.AsyncClient(timeout=8) as client:
            info_res = await client.get(f"{ai_url}/info")
            info = info_res.json() if info_res.status_code == 200 else {}
            models_res = await client.get(f"{ai_url}/models")
            models_data = models_res.json() if models_res.status_code == 200 else {}

        available_models = models_data.get("models", [])
        return {
            "active_provider":      info.get("active_provider", "—"),
            "active_model":         info.get("active_model", "—"),
            "available_providers":  info.get("available_providers", []),
            "fallback_chain":       info.get("fallback_chain", "—"),
            "ollama_url":           info.get("ollama_url", "—"),
            "guardrails_enabled":   info.get("guardrails_enabled", True),
            "agent_timeout":        f"{info.get('agent_timeout_seconds', '—')}s",
            "max_tokens":           info.get("max_tokens", "—"),
            "available_models":     available_models,
            "actions": [
                {"id": "health_check",  "label": "Run Health Check",   "variant": "default", "confirm": False},
                {"id": "reload_models", "label": "Reload Model List",  "variant": "info",    "confirm": False},
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "actions": []}


async def _detail_vault() -> Dict[str, Any]:
    try:
        vault_url = getattr(settings, "VAULT_URL", "http://vault:8200")
        async with httpx.AsyncClient(timeout=5) as client:
            health = (await client.get(f"{vault_url}/v1/sys/health")).json()
        return {
            "version":        health.get("version", "—"),
            "initialized":    health.get("initialized", False),
            "sealed":         health.get("sealed", True),
            "cluster_name":   health.get("cluster_name", "—"),
            "cluster_id":     health.get("cluster_id", "—"),
            "storage_backend": "file",
            "ui_url":         "http://localhost:8200/ui",
            "actions": [
                {"id": "health_check", "label": "Check Status", "variant": "default", "confirm": False},
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "actions": []}


async def _detail_worker(queue_name: str) -> Dict[str, Any]:
    try:
        user, password, host = _rmq_creds()
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(f"http://{host}:15672/api/queues/%2F/{queue_name}", auth=(user, password))
            if res.status_code != 200:
                return {"error": f"Queue '{queue_name}' not found", "actions": []}
            q = res.json()
            consumers_raw = (await client.get(
                f"http://{host}:15672/api/consumers/%2F", auth=(user, password)
            )).json()

        consumers = [
            {
                "tag":        c.get("consumer_tag"),
                "channel":    c.get("channel_details", {}).get("name", "?"),
                "ack_required": c.get("ack_required", True),
            }
            for c in consumers_raw
            if c.get("queue", {}).get("name") == queue_name
        ]

        return {
            "queue":              queue_name,
            "messages_ready":     q.get("messages_ready", 0),
            "messages_unacked":   q.get("messages_unacknowledged", 0),
            "message_rate_in":    q.get("message_stats", {}).get("publish_details", {}).get("rate", 0),
            "message_rate_out":   q.get("message_stats", {}).get("deliver_get_details", {}).get("rate", 0),
            "consumers":          consumers,
            "memory":             q.get("memory", 0),
            "state":              q.get("state", "unknown"),
            "actions": [
                {"id": "purge", "label": f"Purge {queue_name} Queue", "variant": "danger", "confirm": True,
                 "confirm_message": f"This will delete all pending messages from the '{queue_name}' queue."},
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "actions": []}


@router.get("/services/{service_id}/detail")
async def service_detail(
    service_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return rich detail data for a single service."""
    worker_queues = ["nmap", "zap", "trivy", "prowler", "metasploit"]

    if service_id == "postgres":
        return await _detail_postgres(db)
    elif service_id == "redis":
        return await _detail_redis()
    elif service_id == "rabbitmq":
        return await _detail_rabbitmq()
    elif service_id == "elasticsearch":
        return await _detail_elasticsearch()
    elif service_id == "minio":
        return await _detail_minio()
    elif service_id == "ai-engine":
        return await _detail_ai_engine()
    elif service_id == "vault":
        return await _detail_vault()
    else:
        # worker-nmap, worker-zap, etc.
        queue = service_id.replace("worker-", "")
        if queue in worker_queues:
            return await _detail_worker(queue)

    raise HTTPException(status_code=404, detail=f"Unknown service: {service_id}")


# ---------------------------------------------------------------------------
# Service actions
# ---------------------------------------------------------------------------

class ActionRequest(BaseModel):
    action: str
    params: Optional[Dict[str, Any]] = None


@router.post("/services/{service_id}/action")
async def run_service_action(
    service_id: str,
    body: ActionRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Execute a management action on a service."""
    action = body.action

    # ── PostgreSQL ──────────────────────────────────────────────────────────
    if service_id == "postgres":
        if action == "analyze":
            # VACUUM cannot run inside a transaction block — use raw autocommit connection
            raw_conn = db.connection().connection
            old_level = raw_conn.isolation_level
            raw_conn.set_isolation_level(0)  # AUTOCOMMIT
            try:
                raw_conn.cursor().execute("VACUUM ANALYZE")
            finally:
                raw_conn.set_isolation_level(old_level)
            return {"ok": True, "message": "VACUUM ANALYZE completed successfully"}
        elif action == "test":
            db.execute(text("SELECT 1"))
            return {"ok": True, "message": "PostgreSQL connection is healthy"}

    # ── Redis ───────────────────────────────────────────────────────────────
    elif service_id == "redis":
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        if action == "ping":
            r.ping()
            return {"ok": True, "message": "Redis PONG — connection is healthy"}
        elif action == "flush_db":
            r.flushdb()
            return {"ok": True, "message": "Redis DB 0 flushed — all cached keys deleted"}

    # ── RabbitMQ ────────────────────────────────────────────────────────────
    elif service_id == "rabbitmq":
        if action == "purge_all":
            user, password, host = _rmq_creds()
            tool_queues = ["nmap", "zap", "trivy", "prowler", "metasploit"]
            purged = []
            async with httpx.AsyncClient(timeout=5) as client:
                for q in tool_queues:
                    res = await client.delete(
                        f"http://{host}:15672/api/queues/%2F/{q}/contents",
                        auth=(user, password)
                    )
                    if res.status_code in (204, 200):
                        purged.append(q)
            return {"ok": True, "message": f"Purged queues: {', '.join(purged)}"}

    # ── Elasticsearch ───────────────────────────────────────────────────────
    elif service_id == "elasticsearch":
        async with httpx.AsyncClient(timeout=5) as client:
            if action == "refresh":
                await client.post(f"{settings.ELASTICSEARCH_URL}/_refresh")
                return {"ok": True, "message": "All Elasticsearch indices refreshed"}
            elif action == "test":
                res = await client.get(f"{settings.ELASTICSEARCH_URL}/_cluster/health")
                return {"ok": True, "message": f"Cluster status: {res.json().get('status', '?')}"}

    # ── MinIO ───────────────────────────────────────────────────────────────
    elif service_id == "minio":
        if action == "test":
            scheme = "https" if settings.MINIO_SECURE else "http"
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.get(f"{scheme}://{settings.MINIO_ENDPOINT}/minio/health/live")
            return {"ok": res.status_code == 200, "message": "MinIO is reachable" if res.status_code == 200 else "MinIO unreachable"}

    # ── AI Engine ───────────────────────────────────────────────────────────
    elif service_id == "ai-engine":
        ai_url = getattr(settings, "AI_ENGINE_URL", "http://ai-engine:8001")
        async with httpx.AsyncClient(timeout=10) as client:
            if action == "health_check":
                res = await client.get(f"{ai_url}/info")
                data = res.json() if res.status_code == 200 else {}
                provider = data.get("active_provider", "?")
                model = data.get("active_model", "?")
                return {"ok": res.status_code == 200, "message": f"AI Engine healthy · {provider} / {model}"}
            elif action == "reload_models":
                res = await client.get(f"{ai_url}/models")
                data = res.json() if res.status_code == 200 else {}
                count = len(data.get("models", []))
                return {"ok": True, "message": f"Found {count} model(s) available in Ollama"}
            elif action == "change_model":
                params = body.params or {}
                model = params.get("model")
                provider = params.get("provider")
                if not model:
                    return {"ok": False, "message": "No model specified"}
                payload = {"model": model}
                if provider:
                    payload["provider"] = provider
                res = await client.patch(f"{ai_url}/config", json=payload)
                data = res.json() if res.status_code == 200 else {}
                return {
                    "ok": res.status_code == 200,
                    "message": f"Model changed to {data.get('active_model', model)} via {data.get('active_provider', '?')}",
                }

    # ── Vault ────────────────────────────────────────────────────────────────
    elif service_id == "vault":
        vault_url = getattr(settings, "VAULT_URL", "http://vault:8200")
        if action == "health_check":
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.get(f"{vault_url}/v1/sys/health")
                data = res.json() if res.status_code in (200, 429, 472, 473, 501, 503) else {}
                sealed = data.get("sealed", True)
                initialized = data.get("initialized", False)
                state = "unsealed" if (initialized and not sealed) else ("sealed" if initialized else "uninitialized")
                return {"ok": not sealed, "message": f"Vault is {state} · v{data.get('version', '?')}"}

    # ── Workers ─────────────────────────────────────────────────────────────
    else:
        queue = service_id.replace("worker-", "")
        if action == "purge":
            user, password, host = _rmq_creds()
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.delete(
                    f"http://{host}:15672/api/queues/%2F/{queue}/contents",
                    auth=(user, password)
                )
            if res.status_code in (204, 200):
                return {"ok": True, "message": f"Purged all messages from '{queue}' queue"}
            return {"ok": False, "message": f"Purge failed: HTTP {res.status_code}"}

    raise HTTPException(status_code=400, detail=f"Unknown action '{action}' for service '{service_id}'")
