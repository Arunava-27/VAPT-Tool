"""
Elasticsearch fire-and-forget indexer.
All functions are async and designed to be called with asyncio.create_task().
Never raises — silently ignores ES errors so main API is never blocked.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _es_url() -> str:
    from ..core.config import settings
    return getattr(settings, "ELASTICSEARCH_URL", "http://localhost:9200")


async def _es_put(index: str, doc_id: str, body: Dict[str, Any]) -> None:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.put(f"{_es_url()}/{index}/_doc/{doc_id}", json=body)
    except Exception as exc:
        logger.debug(f"ES index skipped ({index}/{doc_id}): {exc}")


async def index_scan(scan) -> None:
    """Index a scan record into vapt-scan-results."""
    summary = scan.result_summary or {}
    findings = summary.get("findings_count", {})
    # Also check flat severity keys workers use
    critical = findings.get("critical") or summary.get("critical", 0) or 0
    high = findings.get("high") or summary.get("high", 0) or 0
    medium = findings.get("medium") or summary.get("medium", 0) or 0
    low = findings.get("low") or summary.get("low", 0) or 0
    total = findings.get("total") or summary.get("total_findings", 0) or 0

    doc = {
        "scan_id": str(scan.id),
        "tenant_id": str(scan.tenant_id) if scan.tenant_id else None,
        "target": scan.target,
        "scan_type": scan.scan_type,
        "status": scan.status,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        "duration_seconds": (
            (scan.completed_at - scan.started_at).total_seconds()
            if scan.completed_at and scan.started_at else None
        ),
        "findings_count": {
            "critical": critical, "high": high,
            "medium": medium, "low": low, "total": total
        },
        "tools_used": summary.get("tools_used", [scan.scan_type]),
    }
    await _es_put("vapt-scan-results", str(scan.id), doc)


async def index_audit_event(log) -> None:
    """Index an audit log into vapt-audit-logs."""
    doc = {
        "log_id": str(log.id),
        "tenant_id": str(log.tenant_id) if log.tenant_id else None,
        "user_id": str(log.user_id) if log.user_id else None,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": str(log.resource_id) if log.resource_id else None,
        "details": log.details or {},
        "ip_address": log.ip_address,
        "user_agent": log.user_agent,
        "created_at": log.created_at.isoformat() if log.created_at else datetime.now(timezone.utc).isoformat(),
    }
    await _es_put("vapt-audit-logs", str(log.id), doc)


async def get_es_status() -> Dict[str, Any]:
    """Check ES cluster health. Returns dict with 'available' bool."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{_es_url()}/_cluster/health")
            data = r.json()
            return {"available": True, "status": data.get("status"), "url": _es_url()}
    except Exception as exc:
        return {"available": False, "error": str(exc), "url": _es_url()}


async def reindex_all(db) -> Dict[str, Any]:
    """Reindex all Postgres data into ES. Called from admin endpoint."""
    from ..models.scan import Scan
    from ..models.audit_log import AuditLog

    scans = db.query(Scan).filter(Scan.status == "completed").all()
    audit_logs = db.query(AuditLog).all()

    tasks = []
    for scan in scans:
        tasks.append(index_scan(scan))
    for log in audit_logs:
        tasks.append(index_audit_event(log))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    return {
        "scans_indexed": len(scans),
        "audit_events_indexed": len(audit_logs),
    }
