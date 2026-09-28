"""Per-user data ownership: competitor tracks and content plan.

Revision ID: 0009_user_tenancy
Revises: 0008_oauth
Create Date: 2026-09-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_user_tenancy"
down_revision: Union[str, Sequence[str], None] = "0008_oauth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_competitor_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "competitor_id", name="uq_user_competitor_track"),
    )
    op.create_index(
        "ix_user_competitor_tracks_user_id",
        "user_competitor_tracks",
        ["user_id"],
    )
    op.create_index(
        "ix_user_competitor_tracks_competitor_id",
        "user_competitor_tracks",
        ["competitor_id"],
    )

    # Fresh per-user plans: drop legacy shared rows, then scope by user.
    op.drop_constraint("uq_content_plan_reel_id", "content_plan_items", type_="unique")
    op.execute("DELETE FROM content_plan_items")
    op.add_column(
        "content_plan_items",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_content_plan_items_user_id",
        "content_plan_items",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_index("ix_content_plan_items_user_id", "content_plan_items", ["user_id"])
    op.create_unique_constraint(
        "uq_content_plan_user_reel",
        "content_plan_items",
        ["user_id", "reel_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_content_plan_user_reel", "content_plan_items", type_="unique")
    op.drop_index("ix_content_plan_items_user_id", table_name="content_plan_items")
    op.drop_constraint("fk_content_plan_items_user_id", "content_plan_items", type_="foreignkey")
    op.drop_column("content_plan_items", "user_id")
    op.create_unique_constraint("uq_content_plan_reel_id", "content_plan_items", ["reel_id"])

    op.drop_index("ix_user_competitor_tracks_competitor_id", table_name="user_competitor_tracks")
    op.drop_index("ix_user_competitor_tracks_user_id", table_name="user_competitor_tracks")
    op.drop_table("user_competitor_tracks")
