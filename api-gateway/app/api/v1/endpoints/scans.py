"""
Scan endpoints - Integrated with Orchestrator
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from ....db.session import get_db
from .auth import get_current_active_user
from ....models.user import User
from ....models.scan import Scan
from ....schemas.scan import (
    ScanCreate,
    ScanUpdate,
    ScanResponse,
    ScanListResponse,
    ScanStatusResponse
)
from ..endpoints.dependencies import PermissionChecker

router = APIRouter()


def dispatch_scan_task(scan_id: str, scan_type: str, target: str, options: dict):
    """Dispatch scan to appropriate Celery worker based on scan type"""
    from celery import Celery
    import os
    
    broker = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672/")
    celery_app = Celery(broker=broker, backend="rpc://")
    
    task_data = {
        "scan_id": scan_id,
        "target": target,
        "options": options
    }
    
    if scan_type == "network":
        result = celery_app.send_task("nmap.scan", args=[task_data], queue="nmap")
    elif scan_type == "web":
        result = celery_app.send_task("zap.scan", args=[task_data], queue="zap")
    elif scan_type == "container":
        result = celery_app.send_task("trivy.scan", args=[task_data], queue="trivy")
    elif scan_type == "cloud":
        result = celery_app.send_task("prowler.scan", args=[task_data], queue="prowler")
    elif scan_type == "full":
        result = celery_app.send_task("nmap.scan", args=[task_data], queue="nmap")
    else:
        result = celery_app.send_task("nmap.scan", args=[task_data], queue="nmap")
    
    return result.id


@router.post(
    "",
    response_model=ScanResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionChecker(["create_scans"]))]
)
async def create_scan(
    scan_data: ScanCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create and start a new scan
    
    Required permission: create_scans
    """
    # Create scan record in database
    scan = Scan(
        name=scan_data.name,
        description=scan_data.description,
        scan_type=scan_data.scan_type.value,
        target=scan_data.targets[0].value if scan_data.targets else "",
        scan_config={
            "targets": [t.dict() for t in scan_data.targets],
            "options": scan_data.options.dict(),
            "priority": scan_data.priority.value
        },
        status="pending",
        tenant_id=str(current_user.tenant_id),
        created_by_id=str(current_user.id)
    )
    
    db.add(scan)
    db.commit()
    db.refresh(scan)
    
    # Dispatch scan task to worker via Celery
    try:
        options = scan_data.options.dict() if scan_data.options else {}
        task_id = dispatch_scan_task(
            scan_id=str(scan.id),
            scan_type=scan_data.scan_type.value,
            target=scan.target,
            options=options
        )
        scan.status = "queued"
        db.commit()
    
    except Exception as e:
        scan.status = "failed"
        scan.error = f"Dispatch error: {str(e)}"
        db.commit()
    
    return scan


@router.get("", response_model=ScanListResponse)
async def list_scans(
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List scans for current user's tenant
    
    Query parameters:
    - skip: Pagination offset
    - limit: Max results (default 100)
    - status_filter: Filter by status (pending, running, completed, etc.)
    """
    # Build query
    query = db.query(Scan).filter(Scan.tenant_id == current_user.tenant_id)
    
    if status_filter:
        query = query.filter(Scan.status == status_filter)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    scans = query.order_by(Scan.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "scans": scans
    }


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(
    scan_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get scan details by ID"""
    scan = db.query(Scan).filter(
        Scan.id == scan_id,
        Scan.tenant_id == current_user.tenant_id
    ).first()
    
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found"
        )
    
    return scan


@router.get("/{scan_id}/status", response_model=ScanStatusResponse)
async def get_scan_status(
    scan_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get real-time scan status and progress"""
    scan = db.query(Scan).filter(
        Scan.id == scan_id,
        Scan.tenant_id == current_user.tenant_id
    ).first()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found"
        )

    result_summary = scan.result_summary or {}

    return {
        "id": scan.id,
        "status": scan.status,
        "progress_percentage": result_summary.get('progress_percentage', 0),
        "current_phase": scan.status,
        "vulnerabilities_found": result_summary.get('total_vulnerabilities', 0),
        "started_at": scan.started_at,
        "completed_at": scan.completed_at,
        "error": scan.error
    }


@router.post(
    "/{scan_id}/cancel",
    response_model=ScanResponse,
    dependencies=[Depends(PermissionChecker(["manage_scans"]))]
)
async def cancel_scan(
    scan_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Cancel a running or queued scan.

    Required permission: manage_scans
    """
    scan = db.query(Scan).filter(
        Scan.id == scan_id,
        Scan.tenant_id == current_user.tenant_id
    ).first()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found"
        )

    cancellable = {'pending', 'queued', 'running', 'preparing', 'scanning', 'analyzing', 'aggregating'}
    if scan.status not in cancellable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel scan with status: {scan.status}"
        )

    scan.status = "cancelled"
    scan.completed_at = datetime.now()
    db.commit()
    db.refresh(scan)

    return scan


@router.delete(
    "/{scan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(PermissionChecker(["manage_scans"]))]
)
async def delete_scan(
    scan_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Permanently delete a scan record."""
    scan = db.query(Scan).filter(
        Scan.id == scan_id,
        Scan.tenant_id == current_user.tenant_id
    ).first()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found"
        )

    db.delete(scan)
    db.commit()
    return None
