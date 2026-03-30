"""
Recon Agent — analyses the target and maps the attack surface.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from .base_agent import AgentResult, BaseAgent
from ..guardrails.guardrail_engine import guardrail_engine


class ReconAgent(BaseAgent):
    agent_name = "recon"

    @property
    def system_prompt(self) -> str:
        return """You are a professional penetration tester performing reconnaissance.
Your job is to analyse a target and produce a structured attack surface map.

Given the target information and any initial scan results, you must:
1. Identify the target type (IP, domain, CIDR, URL, cloud account, container image)
2. Infer likely services and technologies based on open ports and banners
3. Identify potential attack vectors (web, network, cloud, container)
4. Recommend which security tools to prioritise
5. Flag any sensitive assets or high-value targets

Respond ONLY with valid JSON matching this schema:
{
  "target_type": "ip|domain|cidr|url|cloud|container",
  "identified_services": [{"port": 80, "service": "http", "version": "nginx 1.20"}],
  "technologies": ["nginx", "php", "mysql"],
  "attack_vectors": ["web_app", "network", "ssl"],
  "recommended_tools": ["nmap", "zap"],
  "high_value_assets": ["admin panel at /admin", "exposed API"],
  "risk_level": "low|medium|high|critical",
  "notes": "Free-text observations"
}"""

    def run(self, context: Dict[str, Any]) -> AgentResult:
        t0 = time.time()
        target = context.get("target", "")
        scan_type = context.get("scan_type", "network")
        initial_results = context.get("initial_results", {})

        # Validate target via guardrails
        check = guardrail_engine.validate_target(target)
        if not check.allowed:
            return AgentResult(
                agent=self.agent_name, success=False,
                output={}, error=check.reason,
                duration_ms=(time.time() - t0) * 1000
            )

        prompt = f"""Perform reconnaissance analysis for the following target:

Target: {target}
Scan Type: {scan_type}
Initial Scan Data: {initial_results}
Guardrail Risk Level: {check.risk_level}

Produce the attack surface map JSON."""

        try:
            response = self._call_llm(prompt)
            parsed = self._parse_json_response(response.content)
            if not isinstance(parsed, dict):
                parsed = {"raw_response": str(parsed)}

            # Store key findings in shared scan memory
            for asset in parsed.get("high_value_assets") or []:
                self.scan_memory.add_finding({
                    "source": "recon",
                    "severity": parsed.get("risk_level", "medium"),
                    "title": "High-value asset identified",
                    "description": str(asset),
                })

            self.memory.set_state("attack_surface", parsed)
            return AgentResult(
                agent=self.agent_name, success=True, output=parsed,
                reasoning=response.content,
                duration_ms=(time.time() - t0) * 1000,
                llm_provider=response.provider,
            )
        except Exception as e:
            self.logger.error(f"[Recon] Failed: {e}")
            return AgentResult(
                agent=self.agent_name, success=False,
                output={}, error=str(e),
                duration_ms=(time.time() - t0) * 1000,
            )
