"""perf indexes

Revision ID: 422ab8304094
Revises: 45afe14439b1
Create Date: 2025-08-13 20:58:29.726233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '422ab8304094'
down_revision: Union[str, Sequence[str], None] = '45afe14439b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
