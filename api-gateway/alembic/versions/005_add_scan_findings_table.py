"""Add scan_findings table.

Revision ID: 005
Revises: 004
Create Date: 2024-01-01 00:04:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scan_findings",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scan_id", UUID(as_uuid=False), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "vulnerability_id",
            UUID(as_uuid=False),
            sa.ForeignKey("vulnerabilities.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("tool", sa.String(50), nullable=False),
        sa.Column("finding_type", sa.String(100), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("target", sa.String(500), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("service", sa.String(100), nullable=True),
        sa.Column("raw_data", JSONB(), nullable=True),
        sa.Column("ai_analysis", JSONB(), nullable=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("idx_findings_scan", "scan_findings", ["scan_id"])
    op.create_index("idx_findings_severity", "scan_findings", ["severity"])
    op.create_index("idx_findings_tool", "scan_findings", ["tool"])


def downgrade() -> None:
    op.drop_index("idx_findings_tool", table_name="scan_findings")
    op.drop_index("idx_findings_severity", table_name="scan_findings")
    op.drop_index("idx_findings_scan", table_name="scan_findings")
    op.drop_table("scan_findings")
