"""
Roles endpoints — list available roles for user management UI.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from ....db.session import get_db
from ....models.role import Role
from .auth import get_current_active_user
from ....models.user import User

router = APIRouter()


class RoleResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    permissions: list

    class Config:
        from_attributes = True


@router.get("/", response_model=List[RoleResponse])
async def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all active system roles. Requires authentication."""
    import json

    roles = db.query(Role).filter(Role.is_active == True).all()  # noqa: E712
    result = []
    for r in roles:
        raw = r.permissions
        perms = raw if isinstance(raw, list) else (json.loads(raw) if raw else [])
        result.append(RoleResponse(
            id=str(r.id),
            name=r.name,
            slug=r.slug,
            description=r.description,
            permissions=perms,
        ))
    return result
