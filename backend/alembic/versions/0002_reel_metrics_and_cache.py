"""Add reel metrics, source URL, and scrape cache timestamp.

Revision ID: 0002_metrics_cache
Revises: 0001_initial
Create Date: 2026-09-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_metrics_cache"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitors",
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reels",
        sa.Column("instagram_url", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "reels",
        sa.Column(
            "likes_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "reels",
        sa.Column(
            "comments_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "reels",
        sa.Column(
            "shares_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("reels", "shares_count")
    op.drop_column("reels", "comments_count")
    op.drop_column("reels", "likes_count")
    op.drop_column("reels", "instagram_url")
    op.drop_column("competitors", "last_scraped_at")
