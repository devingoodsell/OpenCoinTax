"""add_tax_error_columns

Revision ID: a7f3b2c91d04
Revises: c3a1f7e82d01
Create Date: 2026-02-28 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7f3b2c91d04'
down_revision: Union[str, None] = 'c3a1f7e82d01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tax_error', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('has_tax_error', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        batch_op.create_index('idx_transactions_has_tax_error', ['has_tax_error'])


def downgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_index('idx_transactions_has_tax_error')
        batch_op.drop_column('has_tax_error')
        batch_op.drop_column('tax_error')
