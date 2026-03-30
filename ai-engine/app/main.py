"""
AI Engine FastAPI service — exposes agent pipeline via HTTP.
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import asyncio, uuid, httpx, time as _time

from .engine import AIEngine
from .core.config import settings
from .core.logging import get_logger
from .core.runtime import get as get_runtime, set_override, all_overrides
from .providers.llm_provider import llm_manager, current_queue_depth

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


def _is_cpu_only() -> bool:
    """True when the effective provider is a local CPU-bound backend."""
    return llm_manager.is_cpu_only()


def _estimated_wait_seconds(model: str) -> Optional[int]:
    """Rough estimate of response latency for the current model on CPU."""
    if not _is_cpu_only():
        return None
    m = model.lower()
    if "1b" in m:
        return 45    # llama3.2:1b  — typically 30-60 s on 4 CPU cores
    if "3b" in m or m == "llama3.2" or m == "llama3.2:latest":
        return 210   # llama3.2:3b  — typically 3-4 min on 4 CPU cores
    if "7b" in m:
        return 480   # 7b models     — typically 6-10 min on 4 CPU cores
    return 120       # unknown model — conservative estimate


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-engine"}


@app.get("/info")
def info():
    """Rich status: active provider, model, available providers, config, CPU hints."""
    available = llm_manager.available_providers()
    cpu_only = _is_cpu_only()
    model = _active_model()
    est_wait = _estimated_wait_seconds(model)
    response = {
        "status": "ok",
        "service": "ai-engine",
        "active_provider": _active_provider(),
        "active_model": model,
        "available_providers": available,
        "fallback_chain": settings.LLM_FALLBACK_CHAIN,
        "ollama_url": settings.OLLAMA_BASE_URL,
        "guardrails_enabled": settings.GUARDRAILS_ENABLED,
        "agent_timeout_seconds": settings.AGENT_TIMEOUT_SECONDS,
        "max_tokens": settings.MAX_TOKENS_PER_CALL,
        "concurrency_limit": settings.LLM_CONCURRENCY_LIMIT,
        "queue_depth": current_queue_depth(),
        "runtime_overrides": all_overrides(),
        # CPU inference hints — consumed by the frontend to show warnings
        "is_cpu_only": cpu_only,
        "estimated_wait_seconds": est_wait,
        "ollama_num_threads": settings.OLLAMA_NUM_THREADS if cpu_only else None,
    }
    if cpu_only:
        response["cpu_warning"] = (
            f"CPU-only inference active (model: {model}). "
            f"Expect ~{est_wait}s per response. "
            "Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env for instant cloud inference, "
            "or switch to llama3.2:1b for the fastest local option."
        )
    return response


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
        "is_cpu_only": _is_cpu_only(),
        **({"error": error} if error else {}),
    }


@app.get("/queue")
def queue_status():
    """Current LLM request queue depth and concurrency configuration."""
    return {
        "queue_depth": current_queue_depth(),
        "concurrency_limit": settings.LLM_CONCURRENCY_LIMIT,
        "is_cpu_only": _is_cpu_only(),
        "active_model": _active_model(),
        "estimated_wait_seconds": _estimated_wait_seconds(_active_model()),
    }


@app.patch("/config")
def update_config(update: ConfigUpdate):
    """Change active provider/model at runtime (resets on container restart)."""
    if update.model is not None:
        set_override("model", update.model)
    if update.provider is not None:
        set_override("provider", update.provider)
    model = _active_model()
    return {
        "ok": True,
        "active_provider": _active_provider(),
        "active_model": model,
        "is_cpu_only": _is_cpu_only(),
        "estimated_wait_seconds": _estimated_wait_seconds(model),
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


# ── Chat endpoint ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = []


class ChatResponse(BaseModel):
    response: str
    provider: str
    model: str
    latency_ms: float
    is_cpu_only: bool = False
    estimated_wait_seconds: Optional[int] = None
    queue_depth: int = 0


_CHAT_SYSTEM = """You are a VAPT (Vulnerability Assessment and Penetration Testing) AI assistant built into a security platform.
You help security professionals understand scan results, network topology, vulnerabilities, and provide clear, actionable remediation advice.
Be concise, technical, and professional. Use markdown formatting for lists and code blocks where appropriate.
Keep responses focused and under 600 words unless a detailed explanation is specifically requested."""


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Single-turn (or multi-turn via history) chat with the LLM.

    The blocking LLM call is offloaded to a thread pool via asyncio.to_thread
    so FastAPI's event loop is not blocked while Ollama generates a response.
    The global semaphore in llm_provider.py ensures at most LLM_CONCURRENCY_LIMIT
    requests run concurrently, queuing the rest instead of crashing the CPU.
    """
    from .providers.llm_provider import Message

    messages = [Message(role="system", content=_CHAT_SYSTEM)]

    if req.context:
        messages.append(Message(role="user", content=f"Here is the scan/analysis context to help answer questions:\n\n{req.context}"))
        messages.append(Message(role="assistant", content="I've reviewed the context. How can I help you?"))

    for h in (req.history or []):
        role = h.get("role", "user")
        if role in ("user", "assistant"):
            messages.append(Message(role=role, content=h.get("content", "")))

    messages.append(Message(role="user", content=req.message))

    cpu_only = _is_cpu_only()
    model = _active_model()
    est_wait = _estimated_wait_seconds(model)
    t0 = _time.time()

    try:
        # Run the blocking call in a thread so the event loop stays responsive
        resp = await asyncio.to_thread(llm_manager.complete, messages)
        return ChatResponse(
            response=resp.content,
            provider=resp.provider,
            model=resp.model,
            latency_ms=(_time.time() - t0) * 1000,
            is_cpu_only=cpu_only,
            estimated_wait_seconds=est_wait,
            queue_depth=current_queue_depth(),
        )
    except Exception as e:
        err_str = str(e)
        # Provide actionable guidance in the error message
        if "queue is full" in err_str:
            raise HTTPException(
                status_code=429,
                detail=f"⏳ {err_str}",
            )
        if "timed out" in err_str.lower():
            raise HTTPException(
                status_code=504,
                detail=f"⏱ {err_str}",
            )
        raise HTTPException(status_code=503, detail=err_str)


@app.get("/analyze")
def list_analyses():
    """List all in-memory analysis jobs (newest first)."""
    return [{"job_id": jid, **jdata} for jid, jdata in reversed(list(_jobs.items()))]

