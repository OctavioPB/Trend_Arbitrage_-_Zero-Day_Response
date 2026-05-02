"""Add api_keys table for F4 — Authentication & API Security.

Revision ID: 005
Revises: 004
Create Date: 2026-05-01

key_hash:   bcrypt hash of the full plain key — never store the plain key.
key_prefix: first 12 characters of the plain key (includes 'ta_' prefix);
            used as a DB index to narrow candidates before bcrypt verification.
            Avoids a full table scan on every authenticated request.
scopes:     subset of ['read:signals', 'read:segments', 'write:alerts'].
revoked:    soft-delete; revoked keys return 401 without removing the row.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        # First 12 chars of the plain key — index target for fast lookup
        sa.Column("key_prefix", sa.Text(), nullable=False),
        # bcrypt hash of the full plain key
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="'{}'::text[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoked",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # Fast prefix lookup — narrows candidates before bcrypt verification
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
    # Efficient listing for the management endpoints
    op.create_index("ix_api_keys_owner", "api_keys", ["owner"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_owner", table_name="api_keys")
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
    op.drop_table("api_keys")
