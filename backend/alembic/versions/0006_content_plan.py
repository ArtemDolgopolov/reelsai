"""Add content plan items for shoot workflow.

Revision ID: 0006_content_plan
Revises: 0005_competitor_tracked
Create Date: 2026-09-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_content_plan"
down_revision: Union[str, Sequence[str], None] = "0005_competitor_tracked"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_plan_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "shoot_status",
            sa.String(length=20),
            nullable=False,
            server_default="todo",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["reel_id"], ["reels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reel_id", name="uq_content_plan_reel_id"),
    )
    op.create_index("ix_content_plan_items_reel_id", "content_plan_items", ["reel_id"])
    op.create_index("ix_content_plan_items_shoot_status", "content_plan_items", ["shoot_status"])


def downgrade() -> None:
    op.drop_index("ix_content_plan_items_shoot_status", table_name="content_plan_items")
    op.drop_index("ix_content_plan_items_reel_id", table_name="content_plan_items")
    op.drop_table("content_plan_items")
