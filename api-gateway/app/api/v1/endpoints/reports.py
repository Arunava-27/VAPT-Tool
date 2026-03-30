"""
Reports endpoints — generate, list, download, and delete security scan reports.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ....db.session import get_db
from ....core.config import settings
from .auth import get_current_active_user
from ....models.user import User
from ....models.scan import Scan
from ....models.scan_finding import ScanFinding
from ....models.report import Report
from ....models.network import NetworkNode, HostVulnerability

router = APIRouter()

# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class GenerateReportRequest(BaseModel):
    scan_id: str
    format: str = "html"          # "html" | "json"
    report_type: str = "full"     # "full" | "executive" | "technical"
    title: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _count_severities(findings: List[Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        sev = (f.severity or "info").lower()
        if sev in counts:
            counts[sev] += 1
        else:
            counts["info"] += 1
    return counts


def _finding_to_dict(f: ScanFinding) -> Dict[str, Any]:
    raw = f.raw_data or {}
    description = (
        raw.get("description")
        or raw.get("name")
        or raw.get("title")
        or raw.get("output", "")[:200]
        or ""
    )
    return {
        "id": str(f.id),
        "tool": f.tool,
        "finding_type": f.finding_type,
        "severity": f.severity or "info",
        "target": f.target,
        "port": f.port,
        "service": f.service,
        "description": description,
        "ai_analysis": f.ai_analysis,
    }


def _host_vuln_to_dict(v: HostVulnerability) -> Dict[str, Any]:
    return {
        "id": str(v.id),
        "vuln_id": v.vuln_id,
        "title": v.title,
        "severity": v.severity or "info",
        "description": v.description,
        "cve_id": v.cve_id,
        "cvss_score": v.cvss_score,
        "port": v.port,
        "protocol": v.protocol,
        "service": v.service,
        "evidence": v.evidence,
        "remediation": v.remediation,
        "status": v.status,
    }


def _build_html(report_data: Dict[str, Any]) -> str:
    meta = report_data.get("metadata", {})
    summary = report_data.get("summary", {})
    findings = report_data.get("findings", [])
    network_findings = report_data.get("network_findings", [])
    ai_analysis = report_data.get("ai_analysis") or {}

    title = meta.get("report_title", "Security Report")
    scan_name = meta.get("scan_name", "—")
    scan_target = meta.get("scan_target", "—")
    scan_type = meta.get("scan_type", "—")
    generated_at = meta.get("generated_at", "—")

    def sev_color(sev: str) -> str:
        return {
            "critical": "#e53935",
            "high": "#fb8c00",
            "medium": "#fdd835",
            "low": "#1e88e5",
            "info": "#757575",
        }.get(sev.lower(), "#757575")

    def sev_badge(sev: str) -> str:
        color = sev_color(sev)
        text_color = "#fff" if sev.lower() not in ("medium",) else "#333"
        return (
            f'<span style="background:{color};color:{text_color};'
            f'padding:2px 8px;border-radius:4px;font-size:12px;'
            f'font-weight:600;text-transform:uppercase;">{sev}</span>'
        )

    findings_rows = ""
    for f in sorted(findings, key=lambda x: _SEVERITY_ORDER.get(x.get("severity", "info").lower(), 4)):
        sev = f.get("severity", "info")
        findings_rows += (
            f"<tr>"
            f"<td>{sev_badge(sev)}</td>"
            f"<td>{f.get('finding_type') or '—'}</td>"
            f"<td style='font-family:monospace'>{f.get('target') or '—'}</td>"
            f"<td>{f.get('port') or '—'}</td>"
            f"<td>{f.get('service') or '—'}</td>"
            f"<td>{(f.get('description') or '—')[:120]}</td>"
            f"<td>{f.get('tool') or '—'}</td>"
            f"</tr>\n"
        )

    network_rows = ""
    for v in network_findings:
        sev = v.get("severity", "info")
        network_rows += (
            f"<tr>"
            f"<td>{sev_badge(sev)}</td>"
            f"<td>{v.get('vuln_id') or '—'}</td>"
            f"<td>{v.get('title') or '—'}</td>"
            f"<td>{v.get('cve_id') or '—'}</td>"
            f"<td>{v.get('cvss_score') or '—'}</td>"
            f"<td>{v.get('port') or '—'}</td>"
            f"<td>{(v.get('description') or '—')[:100]}</td>"
            f"</tr>\n"
        )

    summary_boxes = ""
    for sev in ["critical", "high", "medium", "low", "info"]:
        count = summary.get(sev, 0)
        color = sev_color(sev)
        text_color = "#fff" if sev not in ("medium",) else "#333"
        summary_boxes += (
            f'<div style="background:{color};color:{text_color};padding:16px 24px;'
            f'border-radius:8px;text-align:center;min-width:100px;">'
            f'<div style="font-size:32px;font-weight:700">{count}</div>'
            f'<div style="font-size:13px;text-transform:uppercase;margin-top:4px">{sev}</div>'
            f'</div>'
        )

    ai_section = ""
    if ai_analysis:
        ai_text = ai_analysis.get("summary") or json.dumps(ai_analysis, indent=2)
        ai_section = f"""
        <section>
          <h2>AI Analysis</h2>
          <div style="background:#1e2433;padding:16px;border-radius:8px;
                      font-family:monospace;white-space:pre-wrap;font-size:13px;">
            {ai_text}
          </div>
        </section>
        """

    network_section = ""
    if network_findings:
        network_section = f"""
        <section>
          <h2>Network / Host Vulnerabilities</h2>
          <table>
            <thead>
              <tr>
                <th>Severity</th><th>ID</th><th>Title</th>
                <th>CVE</th><th>CVSS</th><th>Port</th><th>Description</th>
              </tr>
            </thead>
            <tbody>
              {network_rows}
            </tbody>
          </table>
        </section>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #0f1117;
      color: #e2e8f0;
      line-height: 1.6;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px; }}
    header {{
      border-bottom: 2px solid #2d3748;
      padding-bottom: 24px;
      margin-bottom: 32px;
    }}
    header h1 {{ font-size: 28px; font-weight: 700; color: #fff; }}
    .meta {{ color: #94a3b8; font-size: 14px; margin-top: 8px; }}
    .meta span {{ margin-right: 24px; }}
    .summary-grid {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 40px;
    }}
    section {{ margin-bottom: 40px; }}
    h2 {{
      font-size: 18px;
      font-weight: 600;
      color: #cbd5e1;
      margin-bottom: 16px;
      padding-bottom: 8px;
      border-bottom: 1px solid #2d3748;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th {{
      background: #1e293b;
      color: #94a3b8;
      text-align: left;
      padding: 10px 12px;
      font-weight: 600;
      text-transform: uppercase;
      font-size: 12px;
      letter-spacing: 0.05em;
    }}
    td {{
      padding: 10px 12px;
      border-bottom: 1px solid #1e293b;
      vertical-align: top;
    }}
    tr:hover td {{ background: #1a2235; }}
    .footer {{
      margin-top: 48px;
      padding-top: 16px;
      border-top: 1px solid #2d3748;
      color: #475569;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>🔒 {title}</h1>
      <div class="meta">
        <span>📡 <strong>Target:</strong> {scan_target}</span>
        <span>🔍 <strong>Scan:</strong> {scan_name}</span>
        <span>🏷 <strong>Type:</strong> {scan_type}</span>
        <span>📅 <strong>Generated:</strong> {generated_at}</span>
      </div>
    </header>

    <section>
      <h2>Findings Summary</h2>
      <div class="summary-grid">
        {summary_boxes}
      </div>
    </section>

    {ai_section}

    <section>
      <h2>Findings ({len(findings)})</h2>
      {"<p style='color:#64748b'>No findings recorded for this scan.</p>" if not findings else f'''
      <table>
        <thead>
          <tr>
            <th>Severity</th><th>Type</th><th>Target</th>
            <th>Port</th><th>Service</th><th>Description</th><th>Tool</th>
          </tr>
        </thead>
        <tbody>
          {findings_rows}
        </tbody>
      </table>'''}
    </section>

    {network_section}

    <div class="footer">
      Generated by VAPT Platform &nbsp;·&nbsp; {generated_at}
    </div>
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
def list_reports(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List all reports for the current user's tenant."""
    reports = (
        db.query(Report)
        .filter(Report.tenant_id == str(current_user.tenant_id))
        .order_by(Report.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "scan_id": r.scan_id,
            "title": r.title,
            "report_type": r.report_type,
            "status": r.status,
            "format": r.format,
            "generated_by": r.generated_by,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in reports
    ]


@router.post("/generate", status_code=201)
def generate_report(
    req: GenerateReportRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Generate a new report for a completed scan."""
    # 1. Fetch the scan (tenant-scoped)
    scan = (
        db.query(Scan)
        .filter(
            Scan.id == req.scan_id,
            Scan.tenant_id == str(current_user.tenant_id),
        )
        .first()
    )
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    # 2. Fetch scan findings
    findings = (
        db.query(ScanFinding)
        .filter(ScanFinding.scan_id == req.scan_id)
        .all()
    )

    # 3. Fetch host vulnerabilities for nodes matching the scan target
    host_vulns: List[HostVulnerability] = []
    if scan.target:
        matching_nodes = (
            db.query(NetworkNode)
            .filter(NetworkNode.ip_address == scan.target)
            .all()
        )
        if matching_nodes:
            node_ids = [str(n.id) for n in matching_nodes]
            host_vulns = (
                db.query(HostVulnerability)
                .filter(HostVulnerability.node_id.in_(node_ids))
                .all()
            )

    # 4. Build structured report dict
    severity_counts = _count_severities(findings)
    result_summary = scan.result_summary or {}
    ai_analysis = result_summary.get("ai_analysis")

    report_data: Dict[str, Any] = {
        "metadata": {
            "report_title": req.title or f"{scan.name} — Security Report",
            "scan_id": str(scan.id),
            "scan_name": scan.name,
            "scan_type": scan.scan_type,
            "scan_target": scan.target,
            "scan_status": scan.status,
            "scan_config": scan.scan_config,
            "report_type": req.report_type,
            "format": req.format,
            "started_at": scan.started_at.isoformat() if scan.started_at else None,
            "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": str(current_user.id),
        },
        "summary": {
            **severity_counts,
            "total": len(findings),
            "network_findings_total": len(host_vulns),
        },
        "findings": [_finding_to_dict(f) for f in findings],
        "network_findings": [_host_vuln_to_dict(v) for v in host_vulns],
        "ai_analysis": ai_analysis,
    }

    # 5 & 6. Format-specific content
    if req.format == "html":
        html_content = _build_html(report_data)
        report_data["html_content"] = html_content

    # 7. Persist Report record
    title = req.title or f"{scan.name} — Security Report"
    report = Report(
        id=str(uuid.uuid4()),
        scan_id=str(scan.id),
        title=title,
        report_type=req.report_type,
        status="ready",
        format=req.format,
        content=report_data,
        generated_by=str(current_user.id),
        tenant_id=str(current_user.tenant_id),
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return {
        "id": report.id,
        "scan_id": report.scan_id,
        "title": report.title,
        "report_type": report.report_type,
        "status": report.status,
        "format": report.format,
        "generated_by": report.generated_by,
        "created_at": report.created_at,
        "summary": report_data["summary"],
    }


@router.get("/{report_id}")
def get_report(
    report_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get a report by ID."""
    report = (
        db.query(Report)
        .filter(
            Report.id == report_id,
            Report.tenant_id == str(current_user.tenant_id),
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/{report_id}/download")
def download_report(
    report_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Download a report. HTML reports are served as HTML; JSON reports as a file attachment."""
    report = (
        db.query(Report)
        .filter(
            Report.id == report_id,
            Report.tenant_id == str(current_user.tenant_id),
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    content = report.content or {}

    if report.format == "html":
        html = content.get("html_content") or _build_html(content)
        return HTMLResponse(content=html, status_code=200)

    # JSON download
    filename = f"report_{report.id}.json"
    json_bytes = json.dumps(content, indent=2, default=str).encode("utf-8")
    from fastapi.responses import Response
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{report_id}", status_code=204)
def delete_report(
    report_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Delete a report."""
    report = (
        db.query(Report)
        .filter(
            Report.id == report_id,
            Report.tenant_id == str(current_user.tenant_id),
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
