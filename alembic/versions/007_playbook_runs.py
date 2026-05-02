"""Add playbook_runs table for F6 — Automated Playbook Engine.

Revision ID: 007
Revises: 006
Create Date: 2026-05-02

Stores every playbook execution attempt (real and dry-run).
topic_cluster is denormalised here so the cooldown query can filter by
playbook_name + topic_cluster without joining golden_records.

status values:
  success  — all action steps completed successfully
  partial  — at least one step failed, at least one succeeded
  error    — all steps failed
  skipped  — trigger did not match OR cooldown was still active
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    op.create_table(
        "playbook_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "golden_record_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("golden_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("playbook_name", sa.Text(), nullable=False),
        sa.Column("topic_cluster", sa.Text(), nullable=False),
        sa.Column(
            "actions_taken",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("dry_run", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            sa.CheckConstraint(
                "status IN ('success','partial','error','skipped')",
                name="ck_pr_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_pr_golden_record_id", "playbook_runs", ["golden_record_id"])
    op.create_index(
        "ix_pr_cooldown",
        "playbook_runs",
        ["playbook_name", "topic_cluster", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pr_cooldown", table_name="playbook_runs")
    op.drop_index("ix_pr_golden_record_id", table_name="playbook_runs")
    op.drop_table("playbook_runs")
