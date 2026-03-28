"""Add reports table.

Revision ID: 003
Revises: 002
Create Date: 2024-01-01 00:02:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scan_id", UUID(as_uuid=False), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("report_type", sa.String(50), server_default=sa.text("'full'"), nullable=True),
        sa.Column("status", sa.String(50), server_default=sa.text("'generating'"), nullable=True),
        sa.Column("format", sa.String(20), server_default=sa.text("'json'"), nullable=True),
        sa.Column("content", JSONB(), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("generated_by", sa.String(50), server_default=sa.text("'ai'"), nullable=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("idx_reports_scan", "reports", ["scan_id"])
    op.create_index("idx_reports_tenant", "reports", ["tenant_id"])
    op.create_index("idx_reports_status", "reports", ["status"])


def downgrade() -> None:
    op.drop_index("idx_reports_status", table_name="reports")
    op.drop_index("idx_reports_tenant", table_name="reports")
    op.drop_index("idx_reports_scan", table_name="reports")
    op.drop_table("reports")
