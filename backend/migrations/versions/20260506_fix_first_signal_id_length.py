"""Fix first_signal_id length for UUID signal ids

Revision ID: 20260506_fix_signal_id_len
Revises: c17aaf851afe
Create Date: 2026-05-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260506_fix_signal_id_len"
down_revision: Union[str, None] = "c17aaf851afe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "work_items",
        "first_signal_id",
        existing_type=sa.String(length=26),
        type_=sa.String(length=36),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "work_items",
        "first_signal_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=26),
        existing_nullable=True,
    )
