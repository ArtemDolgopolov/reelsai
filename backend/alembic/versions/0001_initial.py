"""empty message

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.String(length=1000), nullable=True),
        sa.Column("posts_count", sa.Integer(), nullable=False),
        sa.Column("followers_count", sa.Integer(), nullable=False),
        sa.Column("following_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("pending", "loading", "ready", "error", name="competitorstatus"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("apify_run_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_competitors_username"),
    )
    op.create_index(op.f("ix_competitors_username"), "competitors", ["username"], unique=False)

    op.create_table(
        "reels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=1000), nullable=True),
        sa.Column("video_url", sa.String(length=1000), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("views_count", sa.Integer(), nullable=False),
        sa.Column("overlay_text", sa.String(length=200), nullable=True),
        sa.Column("hook", sa.Text(), server_default="", nullable=False),
        sa.Column("script", sa.Text(), server_default="", nullable=False),
        sa.Column("cta", sa.Text(), server_default="", nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("why_it_works", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.Enum("pending", "ready", "error", name="reelstatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id", name="uq_reels_external_id"),
    )
    op.create_index(op.f("ix_reels_competitor_id"), "reels", ["competitor_id"], unique=False)
    op.create_index(op.f("ix_reels_external_id"), "reels", ["external_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reels_external_id"), table_name="reels")
    op.drop_index(op.f("ix_reels_competitor_id"), table_name="reels")
    op.drop_table("reels")
    op.drop_index(op.f("ix_competitors_username"), table_name="competitors")
    op.drop_table("competitors")
    op.execute("DROP TYPE IF EXISTS reelstatus")
    op.execute("DROP TYPE IF EXISTS competitorstatus")
