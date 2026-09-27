"""Add analysis_overview column for persisted Reels AI explanations.

Revision ID: 0004_analysis_overview
Revises: 0003_widen_urls
Create Date: 2026-09-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_analysis_overview"
down_revision: Union[str, Sequence[str], None] = "0003_widen_urls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reels", sa.Column("analysis_overview", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("reels", "analysis_overview")
