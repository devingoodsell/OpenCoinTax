"""add_koinly_wallet_id_to_wallets

Revision ID: c3a1f7e82d01
Revises: b28996415f95
Create Date: 2026-02-28 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a1f7e82d01'
down_revision: Union[str, None] = 'b28996415f95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('wallets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('koinly_wallet_id', sa.String(length=64), nullable=True))
        batch_op.create_index('idx_wallets_koinly_id', ['koinly_wallet_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('wallets', schema=None) as batch_op:
        batch_op.drop_index('idx_wallets_koinly_id')
        batch_op.drop_column('koinly_wallet_id')
