"""Add kafka_stream_offsets table for F8 — Stream Processing Upgrade.

Revision ID: 009
Revises: 008
Create Date: 2026-05-03

kafka_stream_offsets stores the last successfully committed Kafka offset for
each (consumer_group, topic, partition) triple.

This is a secondary offset store that complements Kafka's internal consumer-group
state. On restart, each streaming service reads from this table and seeks the
consumer to the stored position, giving independent recovery that survives:
  - Kafka log compaction
  - Consumer group metadata loss
  - DB-side rollback recovery (offset is only written after DB write succeeds)

committed_offset is the next offset to consume (i.e., last_processed + 1),
matching Kafka's own committed-offset semantics.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kafka_stream_offsets",
        sa.Column("consumer_group", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("partition", sa.Integer(), nullable=False),
        sa.Column("committed_offset", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("consumer_group", "topic", "partition", name="pk_kso"),
    )


def downgrade() -> None:
    op.drop_table("kafka_stream_offsets")
