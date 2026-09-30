"""baseline execution tables

Revision ID: 0001_execution_tables
Revises:
Create Date: 2026-09-30
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_execution_tables"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "strategy_profiles" not in tables:
        op.create_table(
            "strategy_profiles",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("business_direction", sa.String(length=120), nullable=False),
            sa.Column("primary_objective", sa.String(length=500), nullable=False),
            sa.Column("secondary_objectives", sa.JSON(), nullable=False),
            sa.Column("hard_constraints", sa.JSON(), nullable=False),
            sa.Column("monitoring_config", sa.JSON(), nullable=False),
            sa.Column("allowed_actions", sa.JSON(), nullable=False),
            sa.Column("notification_policy", sa.JSON(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "pending_confirmations" not in tables:
        op.create_table(
            "pending_confirmations",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("recommendation_id", sa.String(length=36), nullable=True),
            sa.Column("action_name", sa.String(length=80), nullable=False),
            sa.Column("action_params", sa.JSON(), nullable=False),
            sa.Column("preview_hash", sa.String(length=64), nullable=False),
            sa.Column("strategy_profile_version", sa.Integer(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_pending_confirmations_idempotency_key",
            "pending_confirmations",
            ["idempotency_key"],
            unique=True,
        )
    if "execution_jobs" not in tables:
        op.create_table(
            "execution_jobs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "confirmation_id",
                sa.String(length=36),
                sa.ForeignKey("pending_confirmations.id"),
                nullable=False,
            ),
            sa.Column("action_name", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("result", sa.JSON(), nullable=False),
        )
        op.create_index("ix_execution_jobs_confirmation_id", "execution_jobs", ["confirmation_id"])
    if "execution_logs" not in tables:
        op.create_table(
            "execution_logs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("job_id", sa.String(length=36), sa.ForeignKey("execution_jobs.id"), nullable=False),
            sa.Column("phase", sa.String(length=32), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("artifact_dir", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_execution_logs_job_id", "execution_logs", ["job_id"])


def downgrade() -> None:
    tables = _tables()
    if "execution_logs" in tables:
        op.drop_table("execution_logs")
    if "execution_jobs" in tables:
        op.drop_table("execution_jobs")
    if "pending_confirmations" in tables:
        op.drop_table("pending_confirmations")