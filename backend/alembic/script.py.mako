# Template used by Alembic when generating new revisions.
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0000"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
