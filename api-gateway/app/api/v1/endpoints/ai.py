"""
AI Engine proxy endpoints — gateway forwards requests to the AI engine service.
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import os, httpx

from .auth import get_current_user  # reuse existing auth dependency

router = APIRouter()

AI_ENGINE_URL = os.getenv("AI_ENGINE_URL", "http://ai-engine:8001")


class AIAnalyzeRequest(BaseModel):
    scan_id: Optional[str] = None
    target: str
    scan_type: str = "network"
    options: Optional[Dict[str, Any]] = {}
    available_tools: Optional[List[str]] = ["nmap", "zap", "trivy", "prowler"]


def _ai_client():
    return httpx.Client(base_url=AI_ENGINE_URL, timeout=30)


@router.post("/analyze")
def start_analysis(req: AIAnalyzeRequest, current_user=Depends(get_current_user)):
    """Kick off an AI-driven analysis pipeline (async)."""
    try:
        with _ai_client() as client:
            resp = client.post("/analyze", json=req.model_dump())
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="AI Engine service unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@router.get("/analyze/{job_id}")
def get_analysis_status(job_id: str, current_user=Depends(get_current_user)):
    """Poll status of a running AI analysis job."""
    try:
        with _ai_client() as client:
            resp = client.get(f"/analyze/{job_id}")
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="AI Engine service unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@router.get("/health")
def ai_engine_health():
    """Check AI engine health (no auth required)."""
    try:
        with _ai_client() as client:
            resp = client.get("/health")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {"status": "unavailable"}
