"""
Scan workflow models and enums
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID, uuid4


class ScanType(str, Enum):
    """Types of scans supported"""
    NETWORK = "network"
    WEB = "web"
    CONTAINER = "container"
    CLOUD = "cloud"
    CUSTOM = "custom"
    COMPREHENSIVE = "comprehensive"  # All applicable tools


class ScanProfile(str, Enum):
    """Scan execution profiles"""
    QUICK = "quick"  # Fast, surface-level scan
    COMPREHENSIVE = "comprehensive"  # Deep, thorough scan
    TARGETED = "targeted"  # Specific targets/checks
    AI_DRIVEN = "ai_driven"  # AI determines scan strategy
    STEALTH = "stealth"  # Evasive scanning
    COMPLIANCE = "compliance"  # Compliance-focused


class ScanStatus(str, Enum):
    """Scan execution status"""
    PENDING = "pending"  # Created, not yet queued
    QUEUED = "queued"  # In queue, waiting for execution
    PREPARING = "preparing"  # Preparing environment
    SCANNING = "scanning"  # Active scanning
    ANALYZING = "analyzing"  # Post-scan analysis
    AGGREGATING = "aggregating"  # Aggregating results
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"  # Failed with errors
    CANCELLED = "cancelled"  # Cancelled by user
    TIMEOUT = "timeout"  # Exceeded time limit


class ScanPriority(str, Enum):
    """Scan priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class WorkerType(str, Enum):
    """Available worker types"""
    NMAP = "nmap"
    ZAP = "zap"
    TRIVY = "trivy"
    PROWLER = "prowler"
    METASPLOIT = "metasploit"


class VulnerabilitySeverity(str, Enum):
    """Vulnerability severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ============================================================================
# Request Models
# ============================================================================

class ScanTarget(BaseModel):
    """Scan target specification"""
    type: str  # ip, domain, url, cidr, container_image, cloud_account
    value: str  # The actual target
    ports: Optional[List[int]] = None
    excludes: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class ScanOptions(BaseModel):
    """Scan configuration options"""
    profile: ScanProfile = ScanProfile.COMPREHENSIVE
    timeout: int = 3600  # seconds
    max_parallel_workers: int = 5
    include_exploits: bool = False
    stealth_mode: bool = False
    custom_options: Optional[Dict[str, Any]] = None


class ScanRequest(BaseModel):
    """User request to create a scan"""
    name: str
    description: Optional[str] = None
    scan_type: ScanType
    targets: List[ScanTarget]
    options: ScanOptions = Field(default_factory=ScanOptions)
    priority: ScanPriority = ScanPriority.NORMAL
    scheduled_at: Optional[datetime] = None
    tenant_id: UUID
    user_id: UUID
    tags: Optional[List[str]] = None


# ============================================================================
# Job Models (Internal Execution State)
# ============================================================================

class WorkerTask(BaseModel):
    """Individual worker task within a scan job"""
    id: UUID = Field(default_factory=uuid4)
    worker_type: WorkerType
    target: ScanTarget
    options: Dict[str, Any] = Field(default_factory=dict)
    status: ScanStatus = ScanStatus.PENDING
    celery_task_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    retry_count: int = 0


class ScanJob(BaseModel):
    """Internal scan job execution state"""
    id: UUID = Field(default_factory=uuid4)
    scan_id: UUID  # References Scan model in database
    name: str
    scan_type: ScanType
    profile: ScanProfile
    status: ScanStatus = ScanStatus.PENDING
    priority: ScanPriority = ScanPriority.NORMAL
    
    # Workflow state
    current_phase: str = "initialization"
    progress_percentage: int = 0
    
    # Tasks
    worker_tasks: List[WorkerTask] = Field(default_factory=list)
    
    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Results
    vulnerabilities_found: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
    
    # Metadata
    tenant_id: UUID
    user_id: UUID
    error: Optional[str] = None
    retry_count: int = 0


# ============================================================================
# Result Models
# ============================================================================

class VulnerabilityFinding(BaseModel):
    """Single vulnerability finding"""
    id: UUID = Field(default_factory=uuid4)
    vulnerability_id: str  # CVE, CWE, or tool-specific ID
    title: str
    description: str
    severity: VulnerabilitySeverity
    cvss_score: Optional[float] = None
    cvss_vector: Optional[str] = None
    
    # Location
    target: str
    host: Optional[str] = None
    port: Optional[int] = None
    service: Optional[str] = None
    url: Optional[str] = None
    path: Optional[str] = None
    
    # Classification
    cve_id: Optional[str] = None
    cwe_id: Optional[str] = None
    category: Optional[str] = None
    
    # Details
    evidence: Optional[str] = None
    proof_of_concept: Optional[str] = None
    remediation: Optional[str] = None
    references: Optional[List[str]] = None
    
    # Source
    tool: str  # Which tool found it
    raw_output: Optional[Dict[str, Any]] = None
    
    # Status
    status: str = "open"  # open, confirmed, false_positive, fixed, accepted
    risk_score: Optional[float] = None
    exploitable: bool = False
    
    # Timestamps
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)


class ScanResult(BaseModel):
    """Aggregated scan results"""
    scan_id: UUID
    scan_job_id: UUID
    status: ScanStatus
    
    # Summary statistics
    total_vulnerabilities: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
    
    # Findings
    vulnerabilities: List[VulnerabilityFinding] = Field(default_factory=list)
    
    # Scan metadata
    scan_duration_seconds: Optional[int] = None
    targets_scanned: int = 0
    tools_used: List[str] = Field(default_factory=list)
    
    # Risk assessment
    overall_risk_score: Optional[float] = None
    risk_level: Optional[str] = None  # critical, high, medium, low
    
    # AI insights (if available)
    ai_summary: Optional[str] = None
    ai_recommendations: Optional[List[str]] = None
    
    # Timestamps
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# State Transition Models
# ============================================================================

class StateTransition(BaseModel):
    """Workflow state transition event"""
    scan_job_id: UUID
    from_status: ScanStatus
    to_status: ScanStatus
    reason: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None


class WorkflowEvent(BaseModel):
    """Workflow lifecycle event"""
    event_type: str  # task_started, task_completed, status_changed, error_occurred
    scan_job_id: UUID
    worker_task_id: Optional[UUID] = None
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
