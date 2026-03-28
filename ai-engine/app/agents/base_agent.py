"""
Base agent — all VAPT agents inherit from this.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..providers.llm_provider import LLMResponse, Message, llm_manager
from ..memory.agent_memory import AgentMemory, ScanMemory
from ..guardrails.guardrail_engine import guardrail_engine
from ..core.config import settings
from ..core.logging import get_logger


@dataclass
class AgentResult:
    agent: str
    success: bool
    output: Dict[str, Any]
    reasoning: str = ""
    error: Optional[str] = None
    duration_ms: float = 0.0
    llm_provider: str = ""


class BaseAgent(ABC):
    """
    Abstract base for all AI agents.
    Provides: LLM access, memory, guardrails, iteration control.
    """

    def __init__(self, scan_id: str):
        self.scan_id = scan_id
        self.memory = AgentMemory(scan_id, self.agent_name)
        self.scan_memory = ScanMemory(scan_id)
        self.logger = get_logger(f"agent.{self.agent_name}")
        self._iterations = 0

    @property
    @abstractmethod
    def agent_name(self) -> str: ...

    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    @abstractmethod
    def run(self, context: Dict[str, Any]) -> AgentResult: ...

    def _call_llm(self, user_message: str, include_history: bool = True, **kwargs) -> LLMResponse:
        """Build message list and call LLM with fallback."""
        messages = [Message(role="system", content=self.system_prompt)]

        if include_history:
            for entry in self.memory.get_history(last_n=10):
                messages.append(Message(role=entry.role if entry.role in ("user", "assistant") else "user",
                                        content=entry.content))

        messages.append(Message(role="user", content=user_message))
        self.memory.add("user", user_message)

        response = llm_manager.complete(messages, **kwargs)

        self.memory.add("assistant", response.content, {"provider": response.provider})
        self.logger.info(f"[{self.agent_name}] LLM response via {response.provider} "
                         f"({response.latency_ms:.0f}ms)")
        return response

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """Extract JSON from LLM response, tolerating markdown code fences."""
        # Strip markdown code fences
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip().rstrip("`").strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try extracting first {...} block
            import re
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
        return {"raw_response": content}

    def _check_iteration_limit(self) -> bool:
        self._iterations += 1
        if self._iterations > settings.MAX_AGENT_ITERATIONS:
            self.logger.warning(f"[{self.agent_name}] Iteration limit reached")
            return False
        return True
