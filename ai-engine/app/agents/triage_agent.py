"""
Triage Agent — prioritises vulnerabilities by risk and business impact.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from .base_agent import AgentResult, BaseAgent


class TriageAgent(BaseAgent):
    agent_name = "triage"

    @property
    def system_prompt(self) -> str:
        return """You are a vulnerability triage specialist with expertise in risk scoring.
Given a list of raw vulnerabilities from security scan tools, you must:
1. Deduplicate findings across tools
2. Assign CVSS-style severity (Critical/High/Medium/Low/Informational)
3. Assess exploitability (Easy/Medium/Hard)
4. Estimate business impact
5. Prioritise for remediation
6. Map to CVE/CWE where possible

Respond ONLY with valid JSON matching this schema:
{
  "triaged_vulnerabilities": [
    {
      "id": "vuln-001",
      "title": "SQL Injection in login form",
      "severity": "Critical",
      "cvss_score": 9.8,
      "cwe": "CWE-89",
      "cve": "N/A",
      "exploitability": "Easy",
      "business_impact": "High — authentication bypass possible",
      "affected_component": "http://target/login",
      "remediation": "Use parameterised queries",
      "priority": 1
    }
  ],
  "summary": {
    "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0,
    "total": 0
  },
  "top_3_priorities": ["vuln-001"],
  "overall_risk": "low|medium|high|critical"
}"""

    def run(self, context: Dict[str, Any]) -> AgentResult:
        t0 = time.time()
        raw_findings: List[Dict] = context.get("raw_findings", [])
        target = context.get("target", "")

        if not raw_findings:
            # Try shared scan memory
            raw_findings = self.scan_memory.get_findings()

        if not raw_findings:
            return AgentResult(
                agent=self.agent_name, success=True,
                output={"triaged_vulnerabilities": [], "summary": {
                    "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "total": 0
                }, "overall_risk": "low"},
                reasoning="No findings to triage.",
                duration_ms=(time.time() - t0) * 1000,
            )

        prompt = f"""Triage the following {len(raw_findings)} vulnerability findings for target: {target}

Raw Findings:
{raw_findings}

Produce the prioritised triage JSON."""

        try:
            response = self._call_llm(prompt)
            parsed = self._parse_json_response(response.content)
            self.memory.set_state("triage_result", parsed)

            # Promote critical findings to shared memory
            for vuln in parsed.get("triaged_vulnerabilities") or []:
                if vuln.get("severity") in ("Critical", "High"):
                    self.scan_memory.add_finding({
                        "source": "triage",
                        "severity": vuln["severity"].lower(),
                        "title": vuln.get("title", "Unknown"),
                        "description": vuln.get("business_impact", ""),
                        "cvss": vuln.get("cvss_score"),
                        "priority": vuln.get("priority"),
                    })

            return AgentResult(
                agent=self.agent_name, success=True, output=parsed,
                reasoning=response.content,
                duration_ms=(time.time() - t0) * 1000,
                llm_provider=response.provider,
            )
        except Exception as e:
            self.logger.error(f"[Triage] Failed: {e}")
            return AgentResult(
                agent=self.agent_name, success=False,
                output={}, error=str(e),
                duration_ms=(time.time() - t0) * 1000,
            )
