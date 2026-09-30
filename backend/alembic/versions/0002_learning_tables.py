"""learning tables

Revision ID: 0002_learning_tables
Revises: 0001_execution_tables
Create Date: 2026-09-30
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_learning_tables"
down_revision: str | None = "0001_execution_tables"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_cases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("strategy_profile_version", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.String(length=36), nullable=True),
        sa.Column("confirmation_id", sa.String(length=36), nullable=True),
        sa.Column("execution_job_id", sa.String(length=36), nullable=True),
        sa.Column("action_name", sa.String(length=80), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "decision_outcomes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("learning_cases.id"), nullable=False),
        sa.Column("metric_window", sa.String(length=16), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_decision_outcomes_case_id", "decision_outcomes", ["case_id"])
    op.create_table(
        "strategy_evaluations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("case_id", sa.String(length=36), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("effect_size", sa.Float(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategy_evaluations_case_id", "strategy_evaluations", ["case_id"])
    op.create_table(
        "strategy_suggestions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("strategy_profile_version", sa.Integer(), nullable=False),
        sa.Column("suggestion_type", sa.String(length=40), nullable=False),
        sa.Column("proposed_change", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("strategy_suggestions")
    op.drop_table("strategy_evaluations")
    op.drop_table("decision_outcomes")
    op.drop_table("learning_cases")