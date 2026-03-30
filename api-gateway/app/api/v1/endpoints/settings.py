"""
Settings endpoints — cloud credential management, host-agent config, platform settings.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, String, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Session

from ....db.session import get_db, Base, engine
from ....core.config import settings
from .auth import get_current_active_user
from ....models.user import User

router = APIRouter()


# ---------------------------------------------------------------------------
# CloudCredential model (inline)
# ---------------------------------------------------------------------------

class CloudCredential(Base):
    """Stores cloud-provider credentials per tenant, encrypted at rest by the DB."""

    __tablename__ = "cloud_credentials"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)   # aws | gcp | azure
    credentials = Column(JSONB, nullable=False, default=dict)   # provider-specific fields
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<CloudCredential(provider={self.provider!r}, tenant={self.tenant_id})>"


# Ensure the table exists (safe to call multiple times)
try:
    CloudCredential.__table__.create(bind=engine, checkfirst=True)
except Exception:
    pass


# ---------------------------------------------------------------------------
# Request / helper schemas
# ---------------------------------------------------------------------------

class CloudCredentialRequest(BaseModel):
    provider: str
    credentials: Dict[str, Any]


class HostAgentRequest(BaseModel):
    url: str


# ---------------------------------------------------------------------------
# Masking helper
# ---------------------------------------------------------------------------

_SECRET_KEYS = {
    "aws": ["secret_access_key"],
    "gcp": ["service_account_json"],
    "azure": ["client_secret"],
}


def _mask(value: str) -> str:
    if not value or len(value) <= 4:
        return "****"
    return "****" + value[-4:]


def _mask_credentials(provider: str, creds: Dict[str, Any]) -> Dict[str, Any]:
    masked = dict(creds)
    for key in _SECRET_KEYS.get(provider, []):
        if key in masked and masked[key]:
            masked[key] = _mask(str(masked[key]))
    return masked


# ---------------------------------------------------------------------------
# Cloud credential endpoints
# ---------------------------------------------------------------------------

@router.get("/cloud-credentials")
def list_cloud_credentials(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List configured cloud providers (secrets are masked)."""
    rows = (
        db.query(CloudCredential)
        .filter(CloudCredential.tenant_id == str(current_user.tenant_id))
        .all()
    )
    return [
        {
            "id": r.id,
            "provider": r.provider,
            "credentials": _mask_credentials(r.provider, r.credentials or {}),
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.post("/cloud-credentials", status_code=201)
def save_cloud_credentials(
    req: CloudCredentialRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Save or update credentials for a cloud provider."""
    if req.provider not in ("aws", "gcp", "azure"):
        raise HTTPException(status_code=400, detail="Provider must be one of: aws, gcp, azure")

    existing = (
        db.query(CloudCredential)
        .filter(
            CloudCredential.tenant_id == str(current_user.tenant_id),
            CloudCredential.provider == req.provider,
        )
        .first()
    )

    if existing:
        existing.credentials = req.credentials
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        record = existing
    else:
        record = CloudCredential(
            id=str(uuid.uuid4()),
            tenant_id=str(current_user.tenant_id),
            provider=req.provider,
            credentials=req.credentials,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    return {
        "id": record.id,
        "provider": record.provider,
        "credentials": _mask_credentials(record.provider, record.credentials or {}),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.delete("/cloud-credentials/{provider}", status_code=204)
def delete_cloud_credentials(
    provider: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Remove credentials for a cloud provider."""
    record = (
        db.query(CloudCredential)
        .filter(
            CloudCredential.tenant_id == str(current_user.tenant_id),
            CloudCredential.provider == provider,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail=f"No credentials found for provider '{provider}'")
    db.delete(record)
    db.commit()


@router.post("/cloud-credentials/{provider}/test")
async def test_cloud_credentials(
    provider: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Test cloud credentials connectivity."""
    record = (
        db.query(CloudCredential)
        .filter(
            CloudCredential.tenant_id == str(current_user.tenant_id),
            CloudCredential.provider == provider,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail=f"No credentials configured for provider '{provider}'")

    creds = record.credentials or {}

    if provider == "aws":
        try:
            import boto3
            from botocore.exceptions import ClientError, NoCredentialsError
            session = boto3.Session(
                aws_access_key_id=creds.get("access_key_id"),
                aws_secret_access_key=creds.get("secret_access_key"),
                region_name=creds.get("region", "us-east-1"),
            )
            sts = session.client("sts")
            identity = sts.get_caller_identity()
            return {
                "ok": True,
                "message": f"AWS credentials valid. Account: {identity.get('Account')}",
                "account_id": identity.get("Account"),
                "arn": identity.get("Arn"),
            }
        except Exception as exc:
            return {"ok": False, "message": f"AWS credential test failed: {exc}"}

    elif provider == "gcp":
        try:
            import json as _json
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request

            sa_json = creds.get("service_account_json", "{}")
            if isinstance(sa_json, str):
                sa_data = _json.loads(sa_json)
            else:
                sa_data = sa_json

            credentials_obj = service_account.Credentials.from_service_account_info(
                sa_data,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            credentials_obj.refresh(Request())
            return {
                "ok": True,
                "message": f"GCP credentials valid. Project: {creds.get('project_id', '—')}",
            }
        except ImportError:
            return {"ok": False, "message": "google-auth library not installed in this environment"}
        except Exception as exc:
            return {"ok": False, "message": f"GCP credential test failed: {exc}"}

    elif provider == "azure":
        try:
            from azure.identity import ClientSecretCredential
            from azure.mgmt.resource import SubscriptionClient

            credential = ClientSecretCredential(
                tenant_id=creds.get("tenant_id"),
                client_id=creds.get("client_id"),
                client_secret=creds.get("client_secret"),
            )
            sub_client = SubscriptionClient(credential)
            subs = list(sub_client.subscriptions.list())
            return {
                "ok": True,
                "message": f"Azure credentials valid. Found {len(subs)} subscription(s).",
            }
        except ImportError:
            return {"ok": False, "message": "azure-mgmt-resource library not installed in this environment"}
        except Exception as exc:
            return {"ok": False, "message": f"Azure credential test failed: {exc}"}

    raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")


# ---------------------------------------------------------------------------
# Host-agent endpoints
# ---------------------------------------------------------------------------

_HOST_AGENT_URL_KEY = "host_agent_url"


def _get_stored_agent_url(db: Session) -> Optional[str]:
    try:
        row = db.execute(
            text("SELECT value FROM platform_settings WHERE key = :key"),
            {"key": _HOST_AGENT_URL_KEY},
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _set_stored_agent_url(db: Session, url: str) -> None:
    try:
        db.execute(
            text(
                """
                INSERT INTO platform_settings (key, value)
                VALUES (:key, :value)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """
            ),
            {"key": _HOST_AGENT_URL_KEY, "value": url},
        )
        db.commit()
    except Exception:
        db.rollback()


@router.get("/host-agent")
async def get_host_agent(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get host agent configuration and live health status."""
    stored_url = _get_stored_agent_url(db)
    agent_url = stored_url or "http://host.docker.internal:9999"

    health_status = "unknown"
    health_detail: Dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(f"{agent_url}/health")
            if res.status_code == 200:
                health_status = "healthy"
                health_detail = res.json()
            else:
                health_status = "unhealthy"
    except Exception as exc:
        health_status = "unreachable"
        health_detail = {"error": str(exc)}

    return {
        "url": agent_url,
        "status": health_status,
        "detail": health_detail,
        "configured": stored_url is not None,
    }


@router.post("/host-agent")
def update_host_agent(
    req: HostAgentRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update the host agent URL."""
    _set_stored_agent_url(db, req.url.rstrip("/"))
    return {"ok": True, "url": req.url.rstrip("/"), "message": "Host agent URL updated"}


# ---------------------------------------------------------------------------
# Platform settings endpoint
# ---------------------------------------------------------------------------

@router.get("/platform")
def get_platform_settings(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get general platform settings."""
    return {
        "platform": "VAPT Tool",
        "version": getattr(settings, "APP_VERSION", "1.0.0"),
        "environment": getattr(settings, "ENVIRONMENT", "production"),
        "ai_engine_url": getattr(settings, "AI_ENGINE_URL", "http://ai-engine:8001"),
        "vault_url": getattr(settings, "VAULT_URL", "http://vault:8200"),
        "elasticsearch_url": getattr(settings, "ELASTICSEARCH_URL", "http://elasticsearch:9200"),
        "minio_endpoint": getattr(settings, "MINIO_ENDPOINT", "minio:9000"),
        "features": {
            "ai_analysis": True,
            "network_discovery": True,
            "cloud_scanning": True,
            "host_agent": True,
        },
    }
