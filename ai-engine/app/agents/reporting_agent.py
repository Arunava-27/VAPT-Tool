"""
Reporting Agent — generates comprehensive, structured security assessment reports.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict

from .base_agent import AgentResult, BaseAgent


class ReportingAgent(BaseAgent):
    agent_name = "reporting"

    @property
    def system_prompt(self) -> str:
        return """You are a senior security consultant writing a professional penetration test report.
The report must be clear, actionable, and appropriate for both technical and executive audiences.

Structure the report as valid JSON with the following sections:
{
  "executive_summary": {
    "overall_risk": "Critical|High|Medium|Low",
    "key_findings": ["Finding 1", "Finding 2"],
    "business_impact": "Summary of business risk",
    "immediate_actions": ["Action 1", "Action 2"]
  },
  "scope": {
    "targets": [],
    "tools_used": [],
    "scan_duration_minutes": 0,
    "scan_date": ""
  },
  "vulnerability_summary": {
    "critical": 0, "high": 0, "medium": 0, "low": 0, "informational": 0,
    "total": 0
  },
  "detailed_findings": [
    {
      "id": "VULN-001",
      "title": "",
      "severity": "",
      "cvss_score": 0.0,
      "description": "",
      "evidence": "",
      "affected_components": [],
      "remediation": "",
      "references": []
    }
  ],
  "remediation_roadmap": [
    {"priority": 1, "action": "", "effort": "low|medium|high", "impact": ""}
  ],
  "technical_appendix": {
    "raw_tool_outputs_summary": "",
    "methodology": ""
  }
}"""

    def run(self, context: Dict[str, Any]) -> AgentResult:
        t0 = time.time()
        target = context.get("target", "")
        scan_id = context.get("scan_id", self.scan_id)
        triage_result = context.get("triage_result", {})
        recon_result = context.get("recon_result", {})
        exploitation_result = context.get("exploitation_result", {})
        scan_duration = context.get("scan_duration_minutes", 0)
        tools_used = context.get("tools_used", [])

        # Supplement with shared memory findings
        all_findings = self.scan_memory.get_findings()

        prompt = f"""Generate a comprehensive penetration test report for:

Scan ID: {scan_id}
Target: {target}
Date: {datetime.utcnow().strftime('%Y-%m-%d')}
Tools Used: {tools_used}
Scan Duration: {scan_duration} minutes

Reconnaissance Summary:
{recon_result}

Triage Results:
{triage_result}

Exploitation Results:
{exploitation_result}

Additional Findings from Memory:
{all_findings[:30]}

Produce the complete report JSON."""

        try:
            response = self._call_llm(prompt, temperature=0.1)
            parsed = self._parse_json_response(response.content)

            # Inject metadata
            parsed.setdefault("scope", {})["scan_date"] = datetime.utcnow().isoformat()
            parsed.setdefault("scope", {})["scan_id"] = scan_id

            self.memory.set_state("report", parsed)
            return AgentResult(
                agent=self.agent_name, success=True, output=parsed,
                reasoning=f"Report generated using {response.provider}",
                duration_ms=(time.time() - t0) * 1000,
                llm_provider=response.provider,
            )
        except Exception as e:
            self.logger.error(f"[Reporting] Failed: {e}")
            return AgentResult(
                agent=self.agent_name, success=False,
                output={}, error=str(e),
                duration_ms=(time.time() - t0) * 1000,
            )
