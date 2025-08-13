"""perf: add indexes for stats

Revision ID: 1162f2686797
Revises: 422ab8304094
Create Date: 2025-08-13 21:01:55.936932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1162f2686797'
down_revision: Union[str, Sequence[str], None] = '422ab8304094'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Speeds WHERE year=... AND round=...
    op.create_index(
        "idx_races_year_round",
        "races",
        ["year", "round"],
        unique=False,
    )
    # Speeds stats joins/filters
    op.create_index(
        "idx_results_driver_race",
        "race_results",
        ["driver_id", "race_id"],
        unique=False,
    )
    op.create_index(
        "idx_results_race",
        "race_results",
        ["race_id"],
        unique=False,
    )

def downgrade() -> None:
    op.drop_index("idx_results_race", table_name="race_results")
    op.drop_index("idx_results_driver_race", table_name="race_results")
    op.drop_index("idx_races_year_round", table_name="races")
