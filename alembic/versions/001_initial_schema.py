"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "enriched_signals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("collected_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "enriched_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column("category", sa.Text()),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("topic_tags", postgresql.ARRAY(sa.Text())),
        sa.Column("sentiment", sa.Text()),
        sa.Column("urgency", sa.Text()),
        sa.Column("engagement_score", sa.Numeric(10, 4)),
        sa.Column("raw_text", sa.Text()),
        sa.Column("url", sa.Text()),
        sa.Column("reasoning", sa.Text()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_enriched_signals_event_id"),
        sa.CheckConstraint(
            "category IN ('opportunity', 'threat', 'noise')",
            name="ck_enriched_signals_category",
        ),
    )
    op.create_index("ix_enriched_signals_collected_at", "enriched_signals", ["collected_at"])
    op.create_index("ix_enriched_signals_category", "enriched_signals", ["category"])
    op.create_index("ix_enriched_signals_urgency", "enriched_signals", ["urgency"])

    op.create_table(
        "golden_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column("topic_cluster", sa.Text(), nullable=False),
        sa.Column("mpi_score", sa.Numeric(4, 3)),
        sa.Column("signal_count", sa.Integer()),
        sa.Column("audience_proxy", postgresql.JSONB()),
        sa.Column("recommended_action", sa.Text()),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_golden_records_topic_cluster", "golden_records", ["topic_cluster"])
    op.create_index("ix_golden_records_expires_at", "golden_records", ["expires_at"])
    op.create_index("ix_golden_records_created_at", "golden_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_golden_records_created_at", table_name="golden_records")
    op.drop_index("ix_golden_records_expires_at", table_name="golden_records")
    op.drop_index("ix_golden_records_topic_cluster", table_name="golden_records")
    op.drop_table("golden_records")

    op.drop_index("ix_enriched_signals_urgency", table_name="enriched_signals")
    op.drop_index("ix_enriched_signals_category", table_name="enriched_signals")
    op.drop_index("ix_enriched_signals_collected_at", table_name="enriched_signals")
    op.drop_table("enriched_signals")
