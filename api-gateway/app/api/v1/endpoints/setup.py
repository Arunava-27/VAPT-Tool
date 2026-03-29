"""
First-run setup endpoints.

These are public (no authentication required). They are only functional
when no superuser exists in the database. Once the super admin is created
they become no-ops (return setup_required: false / 403 respectively).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field, validator
import json

from ....db.session import get_db
from ....models.user import User
from ....models.tenant import Tenant
from ....models.role import Role, SYSTEM_ROLES
from ....core.security import hash_password

router = APIRouter()


class SetupStatusResponse(BaseModel):
    setup_required: bool


class SetupInitRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8)
    confirm_password: str

    @validator("confirm_password")
    def passwords_match(cls, v, values):
        if "password" in values and v != values["password"]:
            raise ValueError("Passwords do not match")
        return v


class SetupInitResponse(BaseModel):
    message: str
    email: str


def _superuser_exists(db: Session) -> bool:
    return db.query(User).filter(User.is_superuser == True).first() is not None  # noqa: E712


def _ensure_tenant_and_roles(db: Session) -> Tenant:
    """Idempotently create default tenant and system roles."""
    tenant = db.query(Tenant).filter(Tenant.slug == "default").first()
    if not tenant:
        tenant = Tenant(
            name="Default Organization",
            slug="default",
            contact_email="admin@vapt-platform.local",
            schema_name="default",
            is_active=True,
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

    for role_slug, role_data in SYSTEM_ROLES.items():
        if not db.query(Role).filter(Role.slug == role_slug).first():
            role = Role(
                name=role_data["name"],
                slug=role_data["slug"],
                description=role_data["description"],
                permissions=role_data["permissions"],
                is_system_role=True,
                is_active=True,
            )
            db.add(role)
    db.commit()
    return db.query(Tenant).filter(Tenant.slug == "default").first()


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(db: Session = Depends(get_db)):
    """
    Returns whether first-run setup is required.
    Frontend calls this on startup to decide whether to show the setup wizard.
    """
    return {"setup_required": not _superuser_exists(db)}


@router.post("/init", response_model=SetupInitResponse, status_code=status.HTTP_201_CREATED)
async def setup_init(data: SetupInitRequest, db: Session = Depends(get_db)):
    """
    Create the first super admin account.
    Only works when no superuser exists — subsequent calls return 403.
    """
    if _superuser_exists(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup already completed. A super admin already exists.",
        )

    # Check email not already taken (edge case: non-super users could exist from a
    # previous partial init)
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already in use.")

    tenant = _ensure_tenant_and_roles(db)
    super_admin_role = db.query(Role).filter(Role.slug == "super_admin").first()

    superuser = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        is_active=True,
        is_superuser=True,
        is_verified=True,
        tenant_id=tenant.id,
    )
    if super_admin_role:
        superuser.roles.append(super_admin_role)

    db.add(superuser)
    db.commit()

    return {"message": "Super admin created successfully. You can now log in.", "email": data.email}
