"""Add performance_events and calibration_proposals tables for F7.

Revision ID: 008
Revises: 007
Create Date: 2026-05-02

performance_events — one row per (golden_record_id, platform, metric, window).
  UNIQUE constraint makes collection idempotent: re-running the collector for
  the same window never produces duplicate rows.

calibration_proposals — proposed MPI_THRESHOLD and source_weight adjustments
  derived from precision analysis. Require explicit human approval before being
  applied. status flow: pending → applied | rejected.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    # ── performance_events ────────────────────────────────────────────────────
    op.create_table(
        "performance_events",
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
        sa.Column(
            "platform",
            sa.Text(),
            sa.CheckConstraint(
                "platform IN ('google_ads', 'meta')",
                name="ck_pe_platform",
            ),
            nullable=False,
        ),
        sa.Column(
            "metric",
            sa.Text(),
            sa.CheckConstraint(
                "metric IN ('ctr', 'conversions', 'impression_share')",
                name="ck_pe_metric",
            ),
            nullable=False,
        ),
        sa.Column("value", sa.Numeric(12, 6), nullable=False),
        sa.Column(
            "measured_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "measurement_window_hours",
            sa.Integer(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "golden_record_id",
            "platform",
            "metric",
            "measurement_window_hours",
            name="uq_pe_record_platform_metric_window",
        ),
    )
    op.create_index("ix_pe_golden_record_id", "performance_events", ["golden_record_id"])
    op.create_index("ix_pe_measured_at", "performance_events", ["measured_at"])

    # ── calibration_proposals ─────────────────────────────────────────────────
    op.create_table(
        "calibration_proposals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("proposed_mpi_threshold", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "proposed_source_weights",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("precision", sa.Numeric(5, 4), nullable=False),
        sa.Column("recall", sa.Numeric(5, 4), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            sa.CheckConstraint(
                "status IN ('pending', 'applied', 'rejected')",
                name="ck_cp_status",
            ),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "proposed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_cp_status_proposed_at",
        "calibration_proposals",
        ["status", "proposed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cp_status_proposed_at", table_name="calibration_proposals")
    op.drop_table("calibration_proposals")

    op.drop_index("ix_pe_measured_at", table_name="performance_events")
    op.drop_index("ix_pe_golden_record_id", table_name="performance_events")
    op.drop_table("performance_events")
