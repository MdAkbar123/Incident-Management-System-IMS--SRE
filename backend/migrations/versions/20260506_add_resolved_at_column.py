"""Add resolved_at column to work_items

Revision ID: 20260506_add_resolved_at
Revises: 20260506_fix_signal_id_len
Create Date: 2026-05-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260506_add_resolved_at"
down_revision: Union[str, None] = "20260506_fix_signal_id_len"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if column exists before adding to avoid duplicate column error
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SHOW COLUMNS FROM work_items LIKE 'resolved_at'")
    )
    if result.rowcount == 0:
        op.add_column(
            "work_items",
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    op.drop_column("work_items", "resolved_at")
