"""
AI Engine Configuration
"""
import os
from typing import Optional, List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service
    SERVICE_NAME: str = "vapt-ai-engine"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # LLM Providers — priority order: openai > anthropic > ollama (local)
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")

    # Local LLM (Ollama) — used when no cloud keys are present (air-gap mode)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    # llama3.2:1b  — ~1.3 GB RAM, ~30-60 s/resp on 4 CPU cores  ← CPU-only default
    # llama3.2     — ~3.8 GB RAM, ~3-5 min/resp on 4 CPU cores
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    OLLAMA_ENABLED: bool = os.getenv("OLLAMA_ENABLED", "true").lower() == "true"

    # CPU performance knobs passed through to Ollama's generate options
    # OLLAMA_NUM_THREADS: pin to the same value as the cpus limit in docker-compose
    #   so Ollama doesn't spin up more threads than it has cores, causing scheduler thrashing.
    OLLAMA_NUM_THREADS: int = int(os.getenv("OLLAMA_NUM_THREADS", "4"))
    OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "5m")

    # LMStudio (alternative local provider)
    LMSTUDIO_BASE_URL: Optional[str] = os.getenv("LMSTUDIO_BASE_URL")
    LMSTUDIO_MODEL: str = os.getenv("LMSTUDIO_MODEL", "local-model")

    # Fallback chain order (comma-separated): openai,anthropic,ollama,lmstudio
    LLM_FALLBACK_CHAIN: str = os.getenv("LLM_FALLBACK_CHAIN", "openai,anthropic,ollama")

    # ── Request-queue / concurrency control ──────────────────────────────────
    # On CPU-only, a single LLM call saturates all cores. Allowing >1 concurrent
    # call causes the kernel scheduler to thrash across threads → ~672% CPU spike.
    # Set to 1 for CPU-only; set to 2-4 if a GPU is present.
    LLM_CONCURRENCY_LIMIT: int = int(os.getenv("LLM_CONCURRENCY_LIMIT", "1"))

    # Redis for memory/state
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/1")
    MEMORY_TTL_SECONDS: int = int(os.getenv("MEMORY_TTL_SECONDS", "3600"))

    # Celery (for async agent tasks)
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672/")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "rpc://")

    # Agent behaviour
    MAX_AGENT_ITERATIONS: int = int(os.getenv("MAX_AGENT_ITERATIONS", "5"))
    # 120 s default — llama3.2:1b typically responds in 30-90 s on 4 CPU cores.
    # Increase to 300 if you switch back to the 3b model.
    AGENT_TIMEOUT_SECONDS: int = int(os.getenv("AGENT_TIMEOUT_SECONDS", "120"))
    # 1024 tokens ≈ ~750 words output — sufficient for VAPT analysis steps.
    # Fewer tokens = faster CPU inference. Increase if truncated responses appear.
    MAX_TOKENS_PER_CALL: int = int(os.getenv("MAX_TOKENS_PER_CALL", "1024"))

    # Safety guardrails
    GUARDRAILS_ENABLED: bool = os.getenv("GUARDRAILS_ENABLED", "true").lower() == "true"
    BLOCKED_TARGETS: List[str] = []   # populated from env or config file

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
