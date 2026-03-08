"""add_coincap_id_to_assets

Revision ID: a1b2c3d4e5f6
Revises: f664ab374f5f
Create Date: 2026-03-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f664ab374f5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('assets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('coincap_id', sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('assets', schema=None) as batch_op:
        batch_op.drop_column('coincap_id')
