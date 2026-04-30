"""Add mpi_history table for F2 — Historical Trend Memory.

Revision ID: 003
Revises: 002
Create Date: 2026-04-30

TimescaleDB note: after running this migration on a TimescaleDB-enabled
instance, optionally run:
    SELECT create_hypertable('mpi_history', 'recorded_at', if_not_exists => TRUE);
Plain PostgreSQL: no action needed — the table works as-is.

Idempotency: the UNIQUE constraint on (recorded_at_bucket, topic_cluster)
enables ON CONFLICT upserts from mpi_archiver.archive_results().
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mpi_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        # Exact timestamp of the computation
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        # 5-minute-aligned bucket — computed in Python before insert
        # Enables idempotency: two runs in the same 5-min window → one row
        sa.Column(
            "recorded_at_bucket",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("topic_cluster", sa.Text(), nullable=False),
        sa.Column("mpi_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False),
        sa.Column(
            "window_minutes",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )

    # Unique constraint drives ON CONFLICT upsert in mpi_archiver
    op.create_unique_constraint(
        "uq_mpi_history_bucket_cluster",
        "mpi_history",
        ["recorded_at_bucket", "topic_cluster"],
    )

    # Supporting baseline aggregation queries
    op.create_index(
        "ix_mpi_history_recorded_at",
        "mpi_history",
        ["recorded_at"],
    )
    op.create_index(
        "ix_mpi_history_topic_cluster_recorded_at",
        "mpi_history",
        ["topic_cluster", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_mpi_history_topic_cluster_recorded_at", table_name="mpi_history")
    op.drop_index("ix_mpi_history_recorded_at", table_name="mpi_history")
    op.drop_constraint("uq_mpi_history_bucket_cluster", "mpi_history", type_="unique")
    op.drop_table("mpi_history")
