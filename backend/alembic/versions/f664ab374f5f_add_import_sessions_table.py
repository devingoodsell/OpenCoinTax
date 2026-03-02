"""add_import_sessions_table

Revision ID: f664ab374f5f
Revises: d4e5f6a7b8c9
Create Date: 2026-03-01 18:40:09.688435

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f664ab374f5f'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('import_sessions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('session_token', sa.String(length=64), nullable=False),
    sa.Column('session_type', sa.String(length=20), nullable=False),
    sa.Column('preview_data', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('import_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_import_sessions_session_token'), ['session_token'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('import_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_import_sessions_session_token'))

    op.drop_table('import_sessions')
