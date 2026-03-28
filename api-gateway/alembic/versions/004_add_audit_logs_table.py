"""Add audit_logs table.

Revision ID: 004
Revises: 003
Create Date: 2024-01-01 00:03:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("details", JSONB(), server_default=sa.text("'{}'"), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("idx_audit_tenant", "audit_logs", ["tenant_id"])
    op.create_index("idx_audit_user", "audit_logs", ["user_id"])
    op.create_index("idx_audit_action", "audit_logs", ["action"])
    op.create_index("idx_audit_created", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_audit_created", table_name="audit_logs")
    op.drop_index("idx_audit_action", table_name="audit_logs")
    op.drop_index("idx_audit_user", table_name="audit_logs")
    op.drop_index("idx_audit_tenant", table_name="audit_logs")
    op.drop_table("audit_logs")
