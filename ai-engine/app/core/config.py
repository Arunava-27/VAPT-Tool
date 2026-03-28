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
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    OLLAMA_ENABLED: bool = os.getenv("OLLAMA_ENABLED", "true").lower() == "true"

    # LMStudio (alternative local provider)
    LMSTUDIO_BASE_URL: Optional[str] = os.getenv("LMSTUDIO_BASE_URL")
    LMSTUDIO_MODEL: str = os.getenv("LMSTUDIO_MODEL", "local-model")

    # Fallback chain order (comma-separated): openai,anthropic,ollama,lmstudio
    LLM_FALLBACK_CHAIN: str = os.getenv("LLM_FALLBACK_CHAIN", "openai,anthropic,ollama")

    # Redis for memory/state
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/1")
    MEMORY_TTL_SECONDS: int = int(os.getenv("MEMORY_TTL_SECONDS", "3600"))

    # Celery (for async agent tasks)
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672/")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "rpc://")

    # Agent behaviour
    MAX_AGENT_ITERATIONS: int = int(os.getenv("MAX_AGENT_ITERATIONS", "10"))
    AGENT_TIMEOUT_SECONDS: int = int(os.getenv("AGENT_TIMEOUT_SECONDS", "300"))
    MAX_TOKENS_PER_CALL: int = int(os.getenv("MAX_TOKENS_PER_CALL", "4096"))

    # Safety guardrails
    GUARDRAILS_ENABLED: bool = os.getenv("GUARDRAILS_ENABLED", "true").lower() == "true"
    BLOCKED_TARGETS: List[str] = []   # populated from env or config file

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
