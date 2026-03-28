"""
Scan Strategy Agent — determines the optimal scan plan.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from .base_agent import AgentResult, BaseAgent


class ScanStrategyAgent(BaseAgent):
    agent_name = "scan_strategy"

    @property
    def system_prompt(self) -> str:
        return """You are a senior penetration testing strategist.
Given reconnaissance data and target context, produce an optimised scan execution plan.

Consider:
- Which tools are most relevant (nmap, zap, trivy, prowler, metasploit)
- Scan ordering (passive → active → exploitation)
- Parallelisation opportunities
- Time and resource constraints
- Stealth requirements (if any)
- Compliance context (PCI-DSS, ISO27001, HIPAA)

Respond ONLY with valid JSON matching this schema:
{
  "scan_phases": [
    {
      "phase": 1,
      "name": "Port Discovery",
      "tools": ["nmap"],
      "parallel": false,
      "options": {"profile": "quick", "ports": "1-1024"},
      "rationale": "Why this phase first"
    }
  ],
  "total_estimated_minutes": 15,
  "stealth_mode": false,
  "priority_vulnerabilities": ["sql_injection", "xss"],
  "skip_tools": [],
  "notes": "Any special considerations"
}"""

    def run(self, context: Dict[str, Any]) -> AgentResult:
        t0 = time.time()
        attack_surface = context.get("attack_surface", {})
        scan_type = context.get("scan_type", "network")
        available_tools = context.get("available_tools", ["nmap", "zap", "trivy", "prowler"])
        options = context.get("options", {})

        prompt = f"""Create an optimised scan strategy for:

Attack Surface: {attack_surface}
Scan Type: {scan_type}
Available Tools: {available_tools}
User Options: {options}

Produce the scan execution plan JSON."""

        try:
            response = self._call_llm(prompt)
            parsed = self._parse_json_response(response.content)
            self.memory.set_state("scan_plan", parsed)
            return AgentResult(
                agent=self.agent_name, success=True, output=parsed,
                reasoning=response.content,
                duration_ms=(time.time() - t0) * 1000,
                llm_provider=response.provider,
            )
        except Exception as e:
            self.logger.error(f"[ScanStrategy] Failed: {e}")
            return AgentResult(
                agent=self.agent_name, success=False,
                output={}, error=str(e),
                duration_ms=(time.time() - t0) * 1000,
            )
