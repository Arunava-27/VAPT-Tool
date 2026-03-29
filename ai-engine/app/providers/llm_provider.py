"""
LLM Provider abstraction — supports OpenAI, Anthropic, Ollama, LMStudio
with automatic fallback chain.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from ..core.config import settings
from ..core.logging import get_logger
from ..core.runtime import get as get_runtime

logger = get_logger(__name__)


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


class BaseLLMProvider(ABC):
    """Abstract LLM provider interface"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def complete(self, messages: List[Message], **kwargs) -> LLMResponse: ...


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def is_available(self) -> bool:
        return bool(settings.OPENAI_API_KEY)

    def complete(self, messages: List[Message], **kwargs) -> LLMResponse:
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

    def complete(self, messages: List[Message], **kwargs) -> LLMResponse:
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
    """Local Ollama provider — works fully air-gapped"""
    name = "ollama"

    def is_available(self) -> bool:
        if not settings.OLLAMA_ENABLED:
            return False
        try:
            import requests
            resp = requests.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def complete(self, messages: List[Message], **kwargs) -> LLMResponse:
        import requests, json
        # Respect runtime model override (set via PATCH /config)
        model = kwargs.get("model") or get_runtime("model") or settings.OLLAMA_MODEL
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": kwargs.get("temperature", 0.2)},
        }
        t0 = time.time()
        resp = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=settings.AGENT_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
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

    def complete(self, messages: List[Message], **kwargs) -> LLMResponse:
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


# Singleton
llm_manager = LLMProviderManager()
