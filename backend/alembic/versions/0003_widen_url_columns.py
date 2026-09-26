"""Widen URL columns to Text for long Instagram CDN links.

Revision ID: 0003_widen_urls
Revises: 0002_metrics_cache
Create Date: 2026-09-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_widen_urls"
down_revision: Union[str, Sequence[str], None] = "0002_metrics_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "competitors",
        "avatar_url",
        existing_type=sa.String(length=1000),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "reels",
        "instagram_url",
        existing_type=sa.String(length=1000),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "reels",
        "thumbnail_url",
        existing_type=sa.String(length=1000),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "reels",
        "video_url",
        existing_type=sa.String(length=1000),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "reels",
        "video_url",
        existing_type=sa.Text(),
        type_=sa.String(length=1000),
        existing_nullable=True,
    )
    op.alter_column(
        "reels",
        "thumbnail_url",
        existing_type=sa.Text(),
        type_=sa.String(length=1000),
        existing_nullable=True,
    )
    op.alter_column(
        "reels",
        "instagram_url",
        existing_type=sa.Text(),
        type_=sa.String(length=1000),
        existing_nullable=True,
    )
    op.alter_column(
        "competitors",
        "avatar_url",
        existing_type=sa.Text(),
        type_=sa.String(length=1000),
        existing_nullable=True,
    )
