"""Add tracked flag for manually saved competitors.

Revision ID: 0005_competitor_tracked
Revises: 0004_analysis_overview
Create Date: 2026-09-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_competitor_tracked"
down_revision: Union[str, Sequence[str], None] = "0004_analysis_overview"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitors",
        sa.Column("tracked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Keep previously loaded real accounts in the saved list (skip discovery autopop).
    op.execute(
        """
        UPDATE competitors
        SET tracked = true
        WHERE username <> 'vibecoding_creator'
          AND (
            bio IS NULL
            OR bio <> 'Автозагрузка для случайной ленты Instagram'
          )
        """
    )


def downgrade() -> None:
    op.drop_column("competitors", "tracked")
