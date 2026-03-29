"""
AI Engine FastAPI service — exposes agent pipeline via HTTP.
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import asyncio, uuid, httpx

from .engine import AIEngine
from .core.config import settings
from .core.logging import get_logger
from .core.runtime import get as get_runtime, set_override, all_overrides
from .providers.llm_provider import llm_manager

logger = get_logger(__name__)
app = FastAPI(title="VAPT AI Engine", version="1.0.0")
engine = AIEngine()

# In-memory job store (replace with DB in production)
_jobs: Dict[str, Dict] = {}


class ScanRequest(BaseModel):
    scan_id: Optional[str] = None
    target: str
    scan_type: str = "network"
    options: Optional[Dict[str, Any]] = {}
    available_tools: Optional[List[str]] = ["nmap", "zap", "trivy", "prowler"]


class ScanStatus(BaseModel):
    job_id: str
    status: str
    result: Optional[Dict[str, Any]] = None


class ConfigUpdate(BaseModel):
    model: Optional[str] = None
    provider: Optional[str] = None


def _active_provider() -> str:
    return get_runtime("provider") or settings.LLM_FALLBACK_CHAIN.split(",")[0].strip()


def _active_model() -> str:
    provider = _active_provider()
    override = get_runtime("model")
    if override:
        return override
    if provider == "openai":
        return settings.OPENAI_MODEL
    if provider == "anthropic":
        return settings.ANTHROPIC_MODEL
    return settings.OLLAMA_MODEL  # default to ollama


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-engine"}


@app.get("/info")
def info():
    """Rich status: active provider, model, available providers, config."""
    available = llm_manager.available_providers()
    return {
        "status": "ok",
        "service": "ai-engine",
        "active_provider": _active_provider(),
        "active_model": _active_model(),
        "available_providers": available,
        "fallback_chain": settings.LLM_FALLBACK_CHAIN,
        "ollama_url": settings.OLLAMA_BASE_URL,
        "guardrails_enabled": settings.GUARDRAILS_ENABLED,
        "agent_timeout_seconds": settings.AGENT_TIMEOUT_SECONDS,
        "max_tokens": settings.MAX_TOKENS_PER_CALL,
        "runtime_overrides": all_overrides(),
    }


@app.get("/models")
async def list_models():
    """List available models (from Ollama) and show the currently active one."""
    models: List[str] = []
    error: Optional[str] = None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if res.status_code == 200:
                models = [m["name"] for m in res.json().get("models", [])]
            else:
                error = f"Ollama returned {res.status_code}"
    except Exception as exc:
        error = str(exc)

    return {
        "provider": _active_provider(),
        "current_model": _active_model(),
        "models": models,
        "ollama_url": settings.OLLAMA_BASE_URL,
        **({"error": error} if error else {}),
    }


@app.patch("/config")
def update_config(update: ConfigUpdate):
    """Change active provider/model at runtime (resets on container restart)."""
    if update.model is not None:
        set_override("model", update.model)
    if update.provider is not None:
        set_override("provider", update.provider)
    return {
        "ok": True,
        "active_provider": _active_provider(),
        "active_model": _active_model(),
    }


@app.post("/analyze", response_model=ScanStatus)
async def analyze(req: ScanRequest, background_tasks: BackgroundTasks):
    """Start an AI-driven analysis pipeline (async)."""
    job_id = req.scan_id or str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "result": None}

    def _run():
        try:
            result = engine.run_scan(
                scan_id=job_id,
                target=req.target,
                scan_type=req.scan_type,
                options=req.options,
                available_tools=req.available_tools,
            )
            _jobs[job_id] = {"status": "completed", "result": result}
        except Exception as e:
            logger.error(f"AI Engine job {job_id} failed: {e}")
            _jobs[job_id] = {"status": "failed", "result": {"error": str(e)}}

    background_tasks.add_task(_run)
    return ScanStatus(job_id=job_id, status="running")


@app.get("/analyze/{job_id}", response_model=ScanStatus)
def get_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return ScanStatus(job_id=job_id, **job)


@app.post("/analyze/{job_id}/sync")
def analyze_sync(req: ScanRequest):
    """Synchronous (blocking) analysis — use for testing."""
    job_id = req.scan_id or str(uuid.uuid4())
    result = engine.run_scan(
        scan_id=job_id,
        target=req.target,
        scan_type=req.scan_type,
        options=req.options,
        available_tools=req.available_tools,
    )
    return result
