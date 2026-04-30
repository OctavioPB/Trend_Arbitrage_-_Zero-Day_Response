"""Add alert_rules table for F1 — Real-time Alerting.

Revision ID: 002
Revises: 001
Create Date: 2026-04-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        # '*' = match all clusters; any other value = exact cluster name
        sa.Column("topic_cluster", sa.Text(), nullable=False, server_default="*"),
        sa.Column(
            "min_mpi",
            sa.Numeric(4, 3),
            nullable=False,
            server_default="0.720",
        ),
        sa.Column("min_signal_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "suppression_minutes",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
        # List of channel configs: [{type: "slack", webhook_url: "..."}, ...]
        sa.Column(
            "channels",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="'[]'::jsonb",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        # Suppression clock — set to NOW() after each successful alert dispatch
        sa.Column(
            "last_alerted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_alert_rules_topic_cluster",
        "alert_rules",
        ["topic_cluster"],
    )
    op.create_index(
        "ix_alert_rules_enabled_min_mpi",
        "alert_rules",
        ["enabled", "min_mpi"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_rules_enabled_min_mpi", table_name="alert_rules")
    op.drop_index("ix_alert_rules_topic_cluster", table_name="alert_rules")
    op.drop_table("alert_rules")
