"""
LLM Provider abstraction — supports OpenAI, Anthropic, Ollama, LMStudio
with automatic fallback chain.

CPU-ONLY OPTIMISATION NOTES
────────────────────────────
• A global threading.Semaphore (size = LLM_CONCURRENCY_LIMIT, default 1) gates
  every provider call.  On CPU-only hardware, allowing > 1 concurrent LLM call
  causes all threads to compete for the same cores, producing scheduler thrashing
  and the observed 672 % CPU spike.  Queuing requests one-at-a-time is always
  faster end-to-end than running two concurrently on a CPU.

• Ollama-specific options forwarded in the request payload:
    num_thread  → pin to OLLAMA_NUM_THREADS (matches the Docker cpus limit)
    num_predict → cap output tokens to MAX_TOKENS_PER_CALL (fewer = faster)
    num_ctx     → context window (512 is fine for structured VAPT queries)
    temperature → low (0.2) for deterministic, structured security output

• keep_alive is passed per-request so the model stays resident between calls
  (avoids the cold-start load on every single request).
"""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from ..core.config import settings
from ..core.logging import get_logger
from ..core.runtime import get as get_runtime

logger = get_logger(__name__)

# ── Concurrency semaphore ─────────────────────────────────────────────────────
# Limits simultaneous LLM calls system-wide.  Default = 1 for CPU-only.
# Adjust LLM_CONCURRENCY_LIMIT env var to allow more parallelism on GPU setups.
_llm_semaphore = threading.Semaphore(max(1, settings.LLM_CONCURRENCY_LIMIT))
_queue_depth: int = 0  # approximate; incremented before acquire, decremented after
_queue_lock = threading.Lock()


def _acquire_slot(timeout: float) -> bool:
    """Try to acquire an LLM execution slot.  Returns False if queue is full."""
    global _queue_depth
    with _queue_lock:
        _queue_depth += 1
    acquired = _llm_semaphore.acquire(timeout=timeout)
    if not acquired:
        with _queue_lock:
            _queue_depth -= 1
    return acquired


def _release_slot() -> None:
    global _queue_depth
    _llm_semaphore.release()
    with _queue_lock:
        _queue_depth = max(0, _queue_depth - 1)


def current_queue_depth() -> int:
    return _queue_depth


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str   # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    raw: Optional[Dict[str, Any]] = field(default=None)


# ── Abstract base ─────────────────────────────────────────────────────────────

class BaseLLMProvider(ABC):
    """Abstract LLM provider interface"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def _complete_impl(self, messages: List[Message], **kwargs) -> LLMResponse: ...

    def complete(self, messages: List[Message], **kwargs) -> LLMResponse:
        """
        Public entry-point.  Acquires the global concurrency semaphore before
        calling the provider-specific _complete_impl so that at most
        LLM_CONCURRENCY_LIMIT requests run concurrently.
        """
        # We allow waiting up to (timeout - 5s) for a slot so that a queued
        # request still has time to execute if it gets the semaphore.
        wait_timeout = max(10.0, settings.AGENT_TIMEOUT_SECONDS - 5)
        if not _acquire_slot(timeout=wait_timeout):
            raise RuntimeError(
                f"LLM request queue is full (concurrency limit = "
                f"{settings.LLM_CONCURRENCY_LIMIT}).  "
                "Another inference is already running on the CPU.  "
                "Please wait a moment and try again."
            )
        try:
            return self._complete_impl(messages, **kwargs)
        finally:
            _release_slot()


# ── Provider implementations ──────────────────────────────────────────────────

class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def is_available(self) -> bool:
        return bool(settings.OPENAI_API_KEY)

    def _complete_impl(self, messages: List[Message], **kwargs) -> LLMResponse:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        t0 = time.time()
        resp = client.chat.completions.create(
            model=kwargs.get("model", settings.OPENAI_MODEL),
            messages=[{"role": m.role, "content": m.content} for m in messages],
            max_tokens=kwargs.get("max_tokens", settings.MAX_TOKENS_PER_CALL),
            temperature=kwargs.get("temperature", 0.2),
        )
        return LLMResponse(
            content=resp.choices[0].message.content,
            provider=self.name,
            model=resp.model,
            prompt_tokens=resp.usage.prompt_tokens,
            completion_tokens=resp.usage.completion_tokens,
            latency_ms=(time.time() - t0) * 1000,
            raw=resp.model_dump(),
        )


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def is_available(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    def _complete_impl(self, messages: List[Message], **kwargs) -> LLMResponse:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        # Separate system message from conversation
        system = next((m.content for m in messages if m.role == "system"), "")
        conv = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        t0 = time.time()
        resp = client.messages.create(
            model=kwargs.get("model", settings.ANTHROPIC_MODEL),
            system=system,
            messages=conv,
            max_tokens=kwargs.get("max_tokens", settings.MAX_TOKENS_PER_CALL),
        )
        return LLMResponse(
            content=resp.content[0].text,
            provider=self.name,
            model=resp.model,
            prompt_tokens=resp.usage.input_tokens,
            completion_tokens=resp.usage.output_tokens,
            latency_ms=(time.time() - t0) * 1000,
        )


class OllamaProvider(BaseLLMProvider):
    """
    Local Ollama provider — works fully air-gapped.

    CPU optimisation options forwarded per request:
      num_thread  — pin threads to OLLAMA_NUM_THREADS to match the Docker CPU quota
      num_predict — cap output to MAX_TOKENS_PER_CALL (fewer tokens = faster inference)
      num_ctx     — context window; 2048 is sufficient for structured VAPT queries
      temperature — 0.2 for deterministic, structured security output
      keep_alive  — keep model resident in RAM between calls (no cold-start penalty)
    """
    name = "ollama"

    def is_available(self) -> bool:
        if not settings.OLLAMA_ENABLED:
            return False
        try:
            import requests
            resp = requests.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def _complete_impl(self, messages: List[Message], **kwargs) -> LLMResponse:
        import requests as req_lib
        # Respect runtime model override (set via PATCH /config)
        model = kwargs.get("model") or get_runtime("model") or settings.OLLAMA_MODEL
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": kwargs.get("temperature", 0.2),
                # Pin threads to match Docker's cpus limit — prevents over-subscription
                "num_thread": settings.OLLAMA_NUM_THREADS,
                # Cap output tokens: fewer = faster CPU inference
                "num_predict": kwargs.get("max_tokens", settings.MAX_TOKENS_PER_CALL),
                # Context window: 2048 is sufficient for structured VAPT queries;
                # reduce to 1024 to save ~200 MB RAM if needed
                "num_ctx": kwargs.get("num_ctx", 2048),
            },
        }
        t0 = time.time()
        try:
            resp = req_lib.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json=payload,
                timeout=settings.AGENT_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
        except req_lib.exceptions.Timeout:
            elapsed = int(time.time() - t0)
            raise RuntimeError(
                f"Ollama timed out after {elapsed}s (limit = {settings.AGENT_TIMEOUT_SECONDS}s). "
                f"Model '{model}' may be too large for CPU-only inference.  "
                "Try switching to llama3.2:1b via PATCH /config or set OLLAMA_MODEL=llama3.2:1b."
            )
        except req_lib.exceptions.ConnectionError:
            raise RuntimeError(
                "Cannot reach Ollama at " + settings.OLLAMA_BASE_URL +
                ".  Ensure the 'ollama' container is running and healthy."
            )
        data = resp.json()
        return LLMResponse(
            content=data["message"]["content"],
            provider=self.name,
            model=model,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            latency_ms=(time.time() - t0) * 1000,
        )


class LMStudioProvider(BaseLLMProvider):
    """LM Studio — OpenAI-compatible local server"""
    name = "lmstudio"

    def is_available(self) -> bool:
        if not settings.LMSTUDIO_BASE_URL:
            return False
        try:
            import requests
            resp = requests.get(f"{settings.LMSTUDIO_BASE_URL}/v1/models", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def _complete_impl(self, messages: List[Message], **kwargs) -> LLMResponse:
        from openai import OpenAI
        client = OpenAI(base_url=f"{settings.LMSTUDIO_BASE_URL}/v1", api_key="lmstudio")
        t0 = time.time()
        resp = client.chat.completions.create(
            model=kwargs.get("model", settings.LMSTUDIO_MODEL),
            messages=[{"role": m.role, "content": m.content} for m in messages],
            max_tokens=kwargs.get("max_tokens", settings.MAX_TOKENS_PER_CALL),
            temperature=kwargs.get("temperature", 0.2),
        )
        return LLMResponse(
            content=resp.choices[0].message.content,
            provider=self.name,
            model=resp.model,
            latency_ms=(time.time() - t0) * 1000,
        )


# ── Registry & manager ────────────────────────────────────────────────────────

# Registry of all providers
_PROVIDER_REGISTRY: Dict[str, BaseLLMProvider] = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "ollama": OllamaProvider(),
    "lmstudio": LMStudioProvider(),
}


class LLMProviderManager:
    """
    Manages the fallback chain. Tries providers in order; falls back
    automatically on failure or unavailability.

    Priority (configured via LLM_FALLBACK_CHAIN env var):
      openai -> anthropic -> ollama -> lmstudio
    """

    def __init__(self):
        chain_names = [n.strip() for n in settings.LLM_FALLBACK_CHAIN.split(",")]
        self._chain: List[BaseLLMProvider] = [
            _PROVIDER_REGISTRY[n] for n in chain_names if n in _PROVIDER_REGISTRY
        ]

    def complete(self, messages: List[Message], **kwargs) -> LLMResponse:
        last_error = None
        for provider in self._chain:
            if not provider.is_available():
                logger.debug(f"[LLM] {provider.name} not available, skipping")
                continue
            try:
                logger.info(f"[LLM] Using provider: {provider.name}")
                return provider.complete(messages, **kwargs)
            except Exception as e:
                logger.warning(f"[LLM] {provider.name} failed: {e}. Trying next.")
                last_error = e
        raise RuntimeError(
            f"All LLM providers exhausted. Last error: {last_error}"
        )

    def available_providers(self) -> List[str]:
        return [p.name for p in self._chain if p.is_available()]

    def is_cpu_only(self) -> bool:
        """Returns True when the active provider is a local CPU-bound backend."""
        available = self.available_providers()
        if not available:
            return False
        first = available[0]
        return first in ("ollama", "lmstudio")


# Singleton
llm_manager = LLMProviderManager()
