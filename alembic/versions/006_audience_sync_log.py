"""Add audience_sync_log table for F5 — Ad Platform Integration.

Revision ID: 006
Revises: 005
Create Date: 2026-05-01

Tracks every attempt to push a Golden Record's audience to an ad platform.
UNIQUE(golden_record_id, platform) enforces idempotency — the same record
cannot be synced to the same platform twice (ON CONFLICT DO UPDATE for retries).

audience_id: the platform's identifier for the created/updated audience.
             NULL for status='error' or status='skipped'.
error_message: redacted at the application layer — never contains credentials.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    op.create_table(
        "audience_sync_log",
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
            sa.CheckConstraint("platform IN ('google_ads', 'meta')", name="ck_asl_platform"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            sa.CheckConstraint("status IN ('success', 'error', 'skipped')", name="ck_asl_status"),
            nullable=False,
        ),
        sa.Column("audience_id", sa.Text(), nullable=True),
        sa.Column(
            "synced_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint("golden_record_id", "platform", name="uq_asl_record_platform"),
    )
    op.create_index(
        "ix_asl_golden_record_id",
        "audience_sync_log",
        ["golden_record_id"],
    )
    op.create_index(
        "ix_asl_platform_status",
        "audience_sync_log",
        ["platform", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_asl_platform_status", table_name="audience_sync_log")
    op.drop_index("ix_asl_golden_record_id", table_name="audience_sync_log")
    op.drop_table("audience_sync_log")
