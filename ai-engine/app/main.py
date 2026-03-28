"""
AI Engine FastAPI service — exposes agent pipeline via HTTP.
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import asyncio, uuid

from .engine import AIEngine
from .core.config import settings
from .core.logging import get_logger

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


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-engine"}


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
