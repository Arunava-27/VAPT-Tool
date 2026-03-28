"""
AI Engine — main orchestrator that runs the full agent pipeline for a scan.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .agents.recon_agent import ReconAgent
from .agents.scan_strategy_agent import ScanStrategyAgent
from .agents.triage_agent import TriageAgent
from .agents.exploitation_agent import ExploitationAgent
from .agents.reporting_agent import ReportingAgent
from .tools.tool_integration import tool_integration
from .memory.agent_memory import ScanMemory
from .guardrails.guardrail_engine import guardrail_engine
from .core.logging import get_logger

logger = get_logger(__name__)


class AIEngine:
    """
    Orchestrates the full AI-driven VAPT pipeline:

    1. Recon Agent      — maps attack surface
    2. Strategy Agent   — builds scan plan
    3. Tool Execution   — dispatches Celery workers
    4. Triage Agent     — prioritises findings
    5. Exploitation Agent (optional, requires authorisation)
    6. Reporting Agent  — generates final report
    """

    def run_scan(
        self,
        scan_id: str,
        target: str,
        scan_type: str = "network",
        options: Optional[Dict[str, Any]] = None,
        available_tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:

        options = options or {}
        available_tools = available_tools or ["nmap", "zap", "trivy", "prowler"]
        scan_memory = ScanMemory(scan_id)
        pipeline_start = time.time()

        logger.info(f"[AIEngine] Starting AI-driven scan {scan_id} for {target}")

        # ── Guardrail pre-check ───────────────────────────────────────────────
        all_ok, warnings = guardrail_engine.validate_scan_scope([target], available_tools)
        if not all_ok:
            return {
                "scan_id": scan_id, "status": "blocked",
                "reason": warnings, "target": target,
            }
        if warnings:
            logger.warning(f"[AIEngine] Guardrail warnings: {warnings}")

        results: Dict[str, Any] = {"scan_id": scan_id, "target": target, "warnings": warnings}

        # ── Phase 1: Recon ────────────────────────────────────────────────────
        logger.info("[AIEngine] Phase 1: Reconnaissance")
        recon = ReconAgent(scan_id)
        recon_result = recon.run({"target": target, "scan_type": scan_type})
        results["recon"] = recon_result.output
        if not recon_result.success:
            logger.warning(f"[AIEngine] Recon failed: {recon_result.error}")

        # ── Phase 2: Scan Strategy ────────────────────────────────────────────
        logger.info("[AIEngine] Phase 2: Scan Strategy")
        strategy = ScanStrategyAgent(scan_id)
        strategy_result = strategy.run({
            "attack_surface": recon_result.output,
            "scan_type": scan_type,
            "available_tools": available_tools,
            "options": options,
        })
        results["strategy"] = strategy_result.output
        scan_plan = strategy_result.output.get("scan_phases", [])

        # ── Phase 3: Tool Execution ───────────────────────────────────────────
        logger.info(f"[AIEngine] Phase 3: Executing {len(scan_plan)} scan phases")
        raw_findings: List[Dict] = []

        for phase in scan_plan:
            phase_tools = phase.get("tools", [])
            phase_opts = phase.get("options", options)
            logger.info(f"[AIEngine] Running phase {phase.get('phase')}: {phase.get('name')} — tools: {phase_tools}")

            for tool in phase_tools:
                if tool not in available_tools:
                    logger.debug(f"[AIEngine] Tool {tool} not available, skipping")
                    continue
                try:
                    result = tool_integration.dispatch_and_wait(
                        tool=tool,
                        target=target,
                        options=phase_opts,
                        scan_id=scan_id,
                        timeout_seconds=int(options.get("timeout", 300)),
                    )
                    tool_findings = result.get("result", {})
                    if isinstance(tool_findings, list):
                        raw_findings.extend(tool_findings)
                    elif isinstance(tool_findings, dict):
                        raw_findings.append(tool_findings)
                    logger.info(f"[AIEngine] {tool} completed for {target}")
                except Exception as e:
                    logger.error(f"[AIEngine] {tool} failed: {e}")
                    raw_findings.append({"tool": tool, "error": str(e), "target": target})

        results["raw_findings"] = raw_findings

        # ── Phase 4: Triage ───────────────────────────────────────────────────
        logger.info("[AIEngine] Phase 4: Triage")
        triage = TriageAgent(scan_id)
        triage_result = triage.run({"target": target, "raw_findings": raw_findings})
        results["triage"] = triage_result.output

        # ── Phase 5: Exploitation (optional) ─────────────────────────────────
        exploitation_result = None
        if options.get("exploitation_authorised", False):
            logger.info("[AIEngine] Phase 5: Exploitation (authorised)")
            exploit = ExploitationAgent(scan_id)
            exploitation_result = exploit.run({
                "target": target,
                "triaged_vulnerabilities": triage_result.output.get("triaged_vulnerabilities", []),
                "exploitation_authorised": True,
            })
            results["exploitation"] = exploitation_result.output

        # ── Phase 6: Report ───────────────────────────────────────────────────
        logger.info("[AIEngine] Phase 6: Report Generation")
        reporter = ReportingAgent(scan_id)
        report_result = reporter.run({
            "scan_id": scan_id,
            "target": target,
            "triage_result": triage_result.output,
            "recon_result": recon_result.output,
            "exploitation_result": (exploitation_result.output if exploitation_result else {}),
            "tools_used": available_tools,
            "scan_duration_minutes": round((time.time() - pipeline_start) / 60, 1),
        })
        results["report"] = report_result.output

        total_duration = round((time.time() - pipeline_start), 1)
        results["status"] = "completed"
        results["duration_seconds"] = total_duration
        logger.info(f"[AIEngine] Scan {scan_id} completed in {total_duration}s")

        return results
