"""Add incident_correlations table for simple dependency-based correlation

Revision ID: 20260506_add_correlations
Revises: 20260506_add_resolved_at
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa


revision = "20260506_add_correlations"
down_revision = "20260506_add_resolved_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_correlations",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("root_incident_id", sa.String(26), sa.ForeignKey("work_items.id"), nullable=False),
        sa.Column("cascaded_incident_id", sa.String(26), sa.ForeignKey("work_items.id"), nullable=False),
        sa.Column("correlation_reason", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_incident_correlations_cascaded", "incident_correlations", ["cascaded_incident_id"])
    op.create_index("ix_incident_correlations_root", "incident_correlations", ["root_incident_id"])


def downgrade() -> None:
    op.drop_index("ix_incident_correlations_root")
    op.drop_index("ix_incident_correlations_cascaded")
    op.drop_table("incident_correlations")
