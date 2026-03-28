"""Initial schema — tenants, roles, users, user_roles, scans.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # tenants
    # ------------------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("schema_name", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("settings", JSONB(), server_default=sa.text("'{}'"), nullable=True),
        sa.Column("max_users", sa.Integer(), server_default=sa.text("10"), nullable=True),
        sa.Column("max_scans", sa.Integer(), server_default=sa.text("100"), nullable=True),
        sa.Column("max_concurrent_scans", sa.Integer(), server_default=sa.text("5"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("idx_tenants_slug", "tenants", ["slug"])
    op.create_index("idx_tenants_name", "tenants", ["name"])

    # ------------------------------------------------------------------
    # roles
    # ------------------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("permissions", JSONB(), server_default=sa.text("'[]'"), nullable=True),
        sa.Column("is_system_role", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("slug", name="uq_roles_slug"),
    )
    op.create_index("idx_roles_slug", "roles", ["slug"])

    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("reset_token", sa.String(255), nullable=True),
        sa.Column("reset_token_expires", sa.DateTime(), nullable=True),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        sa.Column("login_count", sa.String(10), server_default=sa.text("'0'"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_tenant", "users", ["tenant_id"])

    # ------------------------------------------------------------------
    # user_roles
    # ------------------------------------------------------------------
    op.create_table(
        "user_roles",
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", UUID(as_uuid=False), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("assigned_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
    )

    # ------------------------------------------------------------------
    # scans
    # ------------------------------------------------------------------
    op.create_table(
        "scans",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scan_type", sa.String(50), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("status", sa.String(50), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("scan_config", JSONB(), server_default=sa.text("'{}'"), nullable=True),
        sa.Column("result_summary", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_by_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_scans_tenant", "scans", ["tenant_id"])
    op.create_index("idx_scans_status", "scans", ["status"])
    op.create_index("idx_scans_created_by", "scans", ["created_by_id"])
    op.create_index("idx_scans_created_at", "scans", ["created_at"])


def downgrade() -> None:
    op.drop_table("scans")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("roles")
    op.drop_table("tenants")
