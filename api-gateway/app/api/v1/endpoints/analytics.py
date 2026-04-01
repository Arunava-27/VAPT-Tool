"""Analytics endpoints — overview stats, search, audit trail."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text, cast, String
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
import asyncio

from ....db.session import get_db
from .auth import get_current_active_user
from ....models.user import User
from ....models.scan import Scan
from ....models.audit_log import AuditLog
from ....models.vulnerability import Vulnerability

router = APIRouter()


def _safe_int(val) -> int:
    """Safely convert a value to int, returning 0 on failure."""
    try:
        return int(val) if val is not None else 0
    except (ValueError, TypeError):
        return 0


def _extract_severity_totals(scans: list) -> Dict[str, int]:
    """Extract and sum severity counts from scan result_summary JSONB (Python-side)."""
    totals = {"critical": 0, "high": 0, "medium": 0, "low": 0, "informational": 0}
    for scan in scans:
        summary = scan.result_summary or {}
        findings = summary.get("findings_count", {})
        for sev in totals:
            # Try nested findings_count first, then flat keys
            val = findings.get(sev) if findings else None
            if val is None:
                val = summary.get(sev)
            totals[sev] += _safe_int(val)
    return totals


@router.get("/overview")
async def get_overview(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return aggregate analytics overview for the current tenant."""
    tenant_id = str(current_user.tenant_id)

    # Scan counts
    base_q = db.query(Scan).filter(Scan.tenant_id == tenant_id)
    total_scans = base_q.count()
    completed_scans = base_q.filter(Scan.status == "completed").count()
    failed_scans = base_q.filter(Scan.status == "failed").count()
    running_scans = base_q.filter(Scan.status.in_(["running", "queued", "pending"])).count()

    # Severity totals — fetch completed scans and sum Python-side (handles both JSONB layouts)
    completed = base_q.filter(Scan.status == "completed").all()
    severity_totals = _extract_severity_totals(completed)

    # Scan activity last 30 days
    since = datetime.now(timezone.utc) - timedelta(days=30)
    try:
        activity_rows = db.execute(
            text(
                "SELECT DATE(created_at) as date, COUNT(*) as count "
                "FROM scans WHERE created_at >= :since AND tenant_id = :tid "
                "GROUP BY DATE(created_at) ORDER BY date"
            ),
            {"since": since, "tid": tenant_id},
        ).fetchall()
        scan_trend = [{"date": str(r[0]), "count": int(r[1])} for r in activity_rows]
    except Exception:
        scan_trend = []

    # Severity trend last 30 days (Python-side from already-fetched completed scans)
    recent_completed = [s for s in completed if s.created_at and s.created_at.replace(tzinfo=timezone.utc) >= since]
    severity_trend_map: Dict[str, Dict] = {}
    for scan in recent_completed:
        day = str(scan.created_at.date())
        if day not in severity_trend_map:
            severity_trend_map[day] = {"date": day, "critical": 0, "high": 0, "medium": 0, "low": 0}
        summary = scan.result_summary or {}
        findings = summary.get("findings_count", {})
        for sev in ("critical", "high", "medium", "low"):
            val = findings.get(sev) if findings else None
            if val is None:
                val = summary.get(sev)
            severity_trend_map[day][sev] += _safe_int(val)
    severity_trend = sorted(severity_trend_map.values(), key=lambda x: x["date"])

    # Top scan types
    try:
        type_rows = db.execute(
            text(
                "SELECT scan_type, COUNT(*) as count FROM scans "
                "WHERE tenant_id = :tid GROUP BY scan_type ORDER BY count DESC LIMIT 10"
            ),
            {"tid": tenant_id},
        ).fetchall()
        top_scan_types = [{"type": r[0], "count": int(r[1])} for r in type_rows]
    except Exception:
        top_scan_types = []

    # Audit event count
    audit_event_count = db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).count()

    return {
        "total_scans": total_scans,
        "completed_scans": completed_scans,
        "failed_scans": failed_scans,
        "running_scans": running_scans,
        "severity_totals": severity_totals,
        "scan_trend": scan_trend,
        "severity_trend": severity_trend,
        "top_scan_types": top_scan_types,
        "audit_event_count": audit_event_count,
    }


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    types: str = Query(default="scans,vulns,audit"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Full-text search across scans, vulnerabilities, and audit logs."""
    from ....services.es_indexer import get_es_status
    tenant_id = str(current_user.tenant_id)
    type_list = [t.strip() for t in types.split(",")]
    offset = (page - 1) * per_page

    # Try Elasticsearch first
    es_status = await get_es_status()
    if es_status.get("available"):
        try:
            results = await _es_search(q, type_list, tenant_id, offset, per_page)
            if results is not None:
                return results
        except Exception:
            pass

    # Fall back to Postgres
    results_scans: List[Dict] = []
    results_vulns: List[Dict] = []
    results_audit: List[Dict] = []
    total = 0

    if "scans" in type_list:
        q_scans = db.query(Scan).filter(
            Scan.tenant_id == tenant_id,
            (Scan.name.ilike(f"%{q}%") | Scan.target.ilike(f"%{q}%"))
        ).offset(offset).limit(per_page).all()
        results_scans = [
            {
                "id": str(s.id),
                "name": s.name,
                "target": s.target,
                "scan_type": s.scan_type,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in q_scans
        ]
        total += len(results_scans)

    if "vulns" in type_list:
        q_vulns = db.query(Vulnerability).filter(
            Vulnerability.tenant_id == tenant_id,
            (
                Vulnerability.title.ilike(f"%{q}%")
                | Vulnerability.description.ilike(f"%{q}%")
                | Vulnerability.cve.ilike(f"%{q}%")
                | Vulnerability.affected_component.ilike(f"%{q}%")
            ),
        ).offset(offset).limit(per_page).all()
        results_vulns = [
            {
                "id": str(v.id),
                "title": v.title,
                "severity": v.severity,
                "cve": v.cve,
                "affected_component": v.affected_component,
                "scan_id": str(v.scan_id),
                "tool": v.tool,
            }
            for v in q_vulns
        ]
        total += len(results_vulns)

    if "audit" in type_list:
        q_audit = db.query(AuditLog).filter(
            AuditLog.tenant_id == tenant_id,
            (AuditLog.action.ilike(f"%{q}%") | AuditLog.resource_type.ilike(f"%{q}%")),
        ).offset(offset).limit(per_page).all()
        results_audit = [
            {
                "id": a.id,
                "action": a.action,
                "resource_type": a.resource_type,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in q_audit
        ]
        total += len(results_audit)

    return {
        "query": q,
        "source": "postgres",
        "results": {
            "scans": results_scans,
            "vulnerabilities": results_vulns,
            "audit_events": results_audit,
        },
        "total": total,
    }


async def _es_search(q: str, type_list: list, tenant_id: str, offset: int, per_page: int) -> Optional[Dict]:
    """Run multi-search against Elasticsearch. Returns None if ES fails."""
    try:
        import httpx
        from ....services.es_indexer import _es_url

        searches = []
        if "scans" in type_list:
            searches.append({"index": "vapt-scan-results"})
            searches.append({
                "query": {
                    "bool": {
                        "must": {"multi_match": {"query": q, "fields": ["*"]}},
                        "filter": {"term": {"tenant_id": tenant_id}},
                    }
                },
                "from": offset, "size": per_page,
            })
        if "vulns" in type_list:
            searches.append({"index": "vapt-vulnerabilities"})
            searches.append({
                "query": {
                    "bool": {
                        "must": {"multi_match": {"query": q, "fields": ["*"]}},
                        "filter": {"term": {"tenant_id": tenant_id}},
                    }
                },
                "from": offset, "size": per_page,
            })
        if "audit" in type_list:
            searches.append({"index": "vapt-audit-logs"})
            searches.append({
                "query": {
                    "bool": {
                        "must": {"multi_match": {"query": q, "fields": ["*"]}},
                        "filter": {"term": {"tenant_id": tenant_id}},
                    }
                },
                "from": offset, "size": per_page,
            })

        if not searches:
            return None

        body = "\n".join(__import__("json").dumps(s) for s in searches) + "\n"
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(f"{_es_url()}/_msearch", content=body, headers={"Content-Type": "application/x-ndjson"})
            if r.status_code != 200:
                return None
            data = r.json()

        responses = data.get("responses", [])
        results_scans: List[Dict] = []
        results_vulns: List[Dict] = []
        results_audit: List[Dict] = []
        total = 0
        idx = 0

        if "scans" in type_list and idx < len(responses):
            hits = responses[idx].get("hits", {}).get("hits", [])
            for h in hits:
                src = h.get("_source", {})
                results_scans.append({
                    "id": src.get("scan_id", h["_id"]),
                    "name": src.get("name", src.get("target", "")),
                    "target": src.get("target", ""),
                    "scan_type": src.get("scan_type", ""),
                    "status": src.get("status", ""),
                    "created_at": src.get("started_at", ""),
                })
            total += len(results_scans)
            idx += 1

        if "vulns" in type_list and idx < len(responses):
            hits = responses[idx].get("hits", {}).get("hits", [])
            for h in hits:
                src = h.get("_source", {})
                results_vulns.append({
                    "id": src.get("vuln_id", h["_id"]),
                    "title": src.get("title", ""),
                    "severity": src.get("severity", ""),
                    "cve": src.get("cve"),
                    "affected_component": src.get("affected_component"),
                    "scan_id": src.get("scan_id", ""),
                    "tool": src.get("tool", ""),
                })
            total += len(results_vulns)
            idx += 1

        if "audit" in type_list and idx < len(responses):
            hits = responses[idx].get("hits", {}).get("hits", [])
            for h in hits:
                src = h.get("_source", {})
                results_audit.append({
                    "id": src.get("log_id", h["_id"]),
                    "action": src.get("action", ""),
                    "resource_type": src.get("resource_type", ""),
                    "created_at": src.get("created_at", ""),
                })
            total += len(results_audit)

        return {
            "query": q,
            "source": "elasticsearch",
            "results": {
                "scans": results_scans,
                "vulnerabilities": results_vulns,
                "audit_events": results_audit,
            },
            "total": total,
        }
    except Exception:
        return None


@router.get("/audit")
async def get_audit_trail(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    action: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    from_date: Optional[str] = Query(default=None),
    to_date: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Extended audit trail with date range filters."""
    tenant_id = str(current_user.tenant_id)
    q = db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id)

    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if from_date:
        try:
            dt_from = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
            q = q.filter(AuditLog.created_at >= dt_from)
        except ValueError:
            pass
    if to_date:
        try:
            dt_to = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
            q = q.filter(AuditLog.created_at <= dt_to)
        except ValueError:
            pass

    total = q.count()
    entries = (
        q.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Resolve user emails
    user_ids = {e.user_id for e in entries if e.user_id}
    users_map: Dict[str, str] = {}
    if user_ids:
        from ....models.user import User as UserModel
        rows = db.query(UserModel.id, UserModel.email).filter(
            UserModel.id.in_(list(user_ids))
        ).all()
        users_map = {str(r.id): r.email for r in rows}

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "entries": [
            {
                "id": e.id,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "details": e.details or {},
                "user_email": users_map.get(str(e.user_id), "system"),
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ],
    }


@router.get("/es-status")
async def es_status(
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Return Elasticsearch cluster health status."""
    from ....services.es_indexer import get_es_status
    return await get_es_status()


@router.post("/reindex")
async def reindex(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Reindex all Postgres data into Elasticsearch. Admin only."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    from ....services.es_indexer import reindex_all
    return await reindex_all(db)
