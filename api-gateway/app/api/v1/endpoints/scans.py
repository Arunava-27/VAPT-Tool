"""
Scan endpoints - Integrated with Orchestrator
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
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


# Import orchestrator (will be initialized on startup)
orchestrator = None

def get_orchestrator():
    """Get orchestrator instance"""
    global orchestrator
    if orchestrator is None:
        # Import here to avoid circular imports
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../../orchestrator'))
        from app.services.orchestrator import ScanOrchestrator
        orchestrator = ScanOrchestrator()
    return orchestrator


@router.post(
    "/",
    response_model=ScanResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionChecker(["create_scans"]))]
)
async def create_scan(
    scan_data: ScanCreate,
    background_tasks: BackgroundTasks,
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
        scan_type=scan_data.scan_type,
        target=scan_data.targets[0].value if scan_data.targets else "",
        scan_config={
            "targets": [t.dict() for t in scan_data.targets],
            "options": scan_data.options.dict(),
            "priority": scan_data.priority.value
        },
        status="pending",
        tenant_id=current_user.tenant_id,
        created_by_id=current_user.id
    )
    
    db.add(scan)
    db.commit()
    db.refresh(scan)
    
    # Create scan job and start orchestration
    try:
        orch = get_orchestrator()
        
        # Convert to ScanRequest
        from orchestrator.app.models.scan_models import ScanRequest
        scan_request = ScanRequest(
            name=scan_data.name,
            description=scan_data.description,
            scan_type=scan_data.scan_type,
            targets=scan_data.targets,
            options=scan_data.options,
            priority=scan_data.priority,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id
        )
        
        # Create scan job
        scan_job = orch.create_scan(scan_request, scan.id)
        
        # Start scan in background
        background_tasks.add_task(orch.start_scan, scan_job)
        
        # Update scan status
        scan.status = "queued"
        db.commit()
    
    except Exception as e:
        scan.status = "failed"
        scan.error = str(e)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start scan: {e}"
        )
    
    return scan


@router.get("/", response_model=ScanListResponse)
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
    
    # Get live status from orchestrator if scan is active
    live_status = None
    if scan.status in ['queued', 'preparing', 'scanning', 'analyzing', 'aggregating']:
        try:
            orch = get_orchestrator()
            live_status = orch.get_scan_status(scan.id)
        except:
            pass
    
    return {
        "id": scan.id,
        "status": scan.status,
        "progress_percentage": live_status.get('progress_percentage', 0) if live_status else 0,
        "current_phase": live_status.get('current_phase', scan.status) if live_status else scan.status,
        "vulnerabilities_found": (scan.result_summary or {}).get('total_vulnerabilities', 0),
        "started_at": scan.started_at,
        "completed_at": scan.completed_at,
        "error": scan.error
    }


@router.delete(
    "/{scan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(PermissionChecker(["manage_scans"]))]
)
async def cancel_scan(
    scan_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Cancel a running scan
    
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
    
    # Can only cancel active scans
    if scan.status not in ['queued', 'preparing', 'scanning', 'analyzing', 'aggregating']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel scan with status: {scan.status}"
        )
    
    # Cancel in orchestrator
    try:
        orch = get_orchestrator()
        orch.cancel_scan(scan.id, reason="Cancelled by user")
        
        scan.status = "cancelled"
        scan.completed_at = datetime.utcnow()
        db.commit()
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel scan: {e}"
        )
    
    return None
