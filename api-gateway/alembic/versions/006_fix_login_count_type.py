"""Fix login_count column type from VARCHAR to INTEGER.

Revision ID: 006
Revises: 005
Create Date: 2026-03-28 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Must drop the VARCHAR default before casting the type, then restore as INTEGER default.
    op.execute("ALTER TABLE users ALTER COLUMN login_count DROP DEFAULT")
    op.execute(
        "ALTER TABLE users ALTER COLUMN login_count TYPE INTEGER "
        "USING COALESCE(NULLIF(login_count, '')::INTEGER, 0)"
    )
    op.execute("ALTER TABLE users ALTER COLUMN login_count SET DEFAULT 0")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users ALTER COLUMN login_count TYPE VARCHAR(10) "
        "USING login_count::VARCHAR"
    )
    op.execute("ALTER TABLE users ALTER COLUMN login_count SET DEFAULT '0'")
