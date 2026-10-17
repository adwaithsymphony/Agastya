
"""Add preferred language to users.

Revision ID: 0003
Revises: 0002
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add a safe default for existing accounts.
    op.add_column(
        "users",
        sa.Column(
            "preferred_language",
            sa.String(length=5),
            nullable=False,
            server_default="en",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "preferred_language")
