"""
Agent memory — Redis-backed per-scan context store.
Stores conversation history, intermediate findings, and agent state.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import redis

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryEntry:
    role: str        # agent name or "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentMemory:
    """
    Per-scan, per-agent memory backed by Redis.
    Key structure: vapt:memory:{scan_id}:{agent_name}
    """

    def __init__(self, scan_id: str, agent_name: str):
        self.scan_id = scan_id
        self.agent_name = agent_name
        self._key = f"vapt:memory:{scan_id}:{agent_name}"
        self._state_key = f"vapt:state:{scan_id}:{agent_name}"
        try:
            self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            self._redis.ping()
            self._available = True
        except Exception as e:
            logger.warning(f"[Memory] Redis unavailable, using in-process fallback: {e}")
            self._available = False
            self._local: List[dict] = []
            self._local_state: Dict[str, Any] = {}

    # ── Message history ───────────────────────────────────────────────────────

    def add(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        entry = MemoryEntry(role=role, content=content, metadata=metadata or {})
        serialized = json.dumps(asdict(entry))
        if self._available:
            self._redis.rpush(self._key, serialized)
            self._redis.expire(self._key, settings.MEMORY_TTL_SECONDS)
        else:
            self._local.append(asdict(entry))

    def get_history(self, last_n: Optional[int] = None) -> List[MemoryEntry]:
        if self._available:
            raw = self._redis.lrange(self._key, 0, -1)
            entries = [MemoryEntry(**json.loads(r)) for r in raw]
        else:
            entries = [MemoryEntry(**e) for e in self._local]
        return entries[-last_n:] if last_n else entries

    def clear(self) -> None:
        if self._available:
            self._redis.delete(self._key, self._state_key)
        else:
            self._local.clear()
            self._local_state.clear()

    # ── Key-value state store ─────────────────────────────────────────────────

    def set_state(self, key: str, value: Any) -> None:
        if self._available:
            data = self._redis.get(self._state_key)
            state = json.loads(data) if data else {}
            state[key] = value
            self._redis.setex(self._state_key, settings.MEMORY_TTL_SECONDS, json.dumps(state))
        else:
            self._local_state[key] = value

    def get_state(self, key: str, default: Any = None) -> Any:
        if self._available:
            data = self._redis.get(self._state_key)
            return json.loads(data).get(key, default) if data else default
        return self._local_state.get(key, default)

    def get_all_state(self) -> Dict[str, Any]:
        if self._available:
            data = self._redis.get(self._state_key)
            return json.loads(data) if data else {}
        return dict(self._local_state)


class ScanMemory:
    """
    Shared scan-level memory — stores findings visible to all agents.
    """

    def __init__(self, scan_id: str):
        self.scan_id = scan_id
        self._key = f"vapt:scan:{scan_id}:findings"
        try:
            self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            self._redis.ping()
            self._available = True
        except Exception:
            self._available = False
            self._local: List[dict] = []

    def add_finding(self, finding: Dict[str, Any]) -> None:
        finding["timestamp"] = time.time()
        serialized = json.dumps(finding)
        if self._available:
            self._redis.rpush(self._key, serialized)
            self._redis.expire(self._key, settings.MEMORY_TTL_SECONDS)
        else:
            self._local.append(finding)

    def get_findings(self) -> List[Dict[str, Any]]:
        if self._available:
            raw = self._redis.lrange(self._key, 0, -1)
            return [json.loads(r) for r in raw]
        return list(self._local)

    def summary(self) -> str:
        findings = self.get_findings()
        if not findings:
            return "No findings yet."
        lines = [f"- [{f.get('severity','?')}] {f.get('title','unknown')}: {f.get('description','')}"
                 for f in findings[:20]]
        return "\n".join(lines)
