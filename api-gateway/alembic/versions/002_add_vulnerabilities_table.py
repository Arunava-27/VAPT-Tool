"""Add vulnerabilities table.

Revision ID: 002
Revises: 001
Create Date: 2024-01-01 00:01:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vulnerabilities",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scan_id", UUID(as_uuid=False), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("cvss_score", sa.Float(), nullable=True),
        sa.Column("cwe", sa.String(50), nullable=True),
        sa.Column("cve", sa.String(50), nullable=True),
        sa.Column("affected_component", sa.String(500), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), server_default=sa.text("'open'"), nullable=True),
        sa.Column("tool", sa.String(50), nullable=True),
        sa.Column("raw_output", JSONB(), nullable=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("idx_vulns_scan", "vulnerabilities", ["scan_id"])
    op.create_index("idx_vulns_severity", "vulnerabilities", ["severity"])
    op.create_index("idx_vulns_status", "vulnerabilities", ["status"])
    op.create_index("idx_vulns_tenant", "vulnerabilities", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_vulns_tenant", table_name="vulnerabilities")
    op.drop_index("idx_vulns_status", table_name="vulnerabilities")
    op.drop_index("idx_vulns_severity", table_name="vulnerabilities")
    op.drop_index("idx_vulns_scan", table_name="vulnerabilities")
    op.drop_table("vulnerabilities")
