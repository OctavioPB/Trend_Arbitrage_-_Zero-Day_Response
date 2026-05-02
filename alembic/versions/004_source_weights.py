"""Add source_weight column to enriched_signals for F3 — Ingestion Expansion.

Revision ID: 004
Revises: 003
Create Date: 2026-05-01

source_weight stores the per-source multiplier that was in effect at enrichment
time (read from config/source_weights.json). The MPI calculator reads weights
directly from source_weights.json at computation time; this column exists for
auditing and replay purposes.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "enriched_signals",
        sa.Column(
            "source_weight",
            sa.Numeric(3, 2),
            nullable=False,
            server_default="1.00",
        ),
    )


def downgrade() -> None:
    op.drop_column("enriched_signals", "source_weight")
