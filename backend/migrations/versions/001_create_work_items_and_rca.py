"""create work_items and rca tables

Revision ID: 001
Revises:
Create Date: 2026-05-03
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column("id",             sa.String(26),    primary_key=True),
        sa.Column("component_id",   sa.String(100),   nullable=False),
        sa.Column("component_type", sa.Enum("API","MCP_HOST","CACHE","ASYNC_QUEUE","RDBMS","NOSQL"), nullable=False),
        sa.Column("priority",       sa.Enum("P0","P1","P2"), nullable=False),
        sa.Column("status",         sa.Enum("OPEN","INVESTIGATING","RESOLVED","CLOSED"), nullable=False, server_default="OPEN"),
        sa.Column("first_signal_id",sa.String(36),    nullable=True),
        sa.Column("signal_count",   sa.Integer(),     nullable=False, server_default="1"),
        sa.Column("created_at",     sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",     sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at",    sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_work_items_component_id", "work_items", ["component_id"])

    op.create_table(
        "rca",
        sa.Column("id",                  sa.String(26), primary_key=True),
        sa.Column("work_item_id",        sa.String(26), sa.ForeignKey("work_items.id"), nullable=False, unique=True),
        sa.Column("start_time",          sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time",            sa.DateTime(timezone=True), nullable=False),
        sa.Column("root_cause_category", sa.Enum("INFRASTRUCTURE","CODE_BUG","CONFIG_CHANGE","DEPENDENCY_FAILURE","UNKNOWN"), nullable=False),
        sa.Column("fix_applied",         sa.Text(), nullable=False),
        sa.Column("prevention_steps",    sa.Text(), nullable=False),
        sa.Column("mttr_seconds",        sa.Float(), nullable=False),
        sa.Column("submitted_at",        sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

def downgrade() -> None:
    op.drop_table("rca")
    op.drop_table("work_items")
