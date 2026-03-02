"""seed default data

Revision ID: 96e87b774682
Revises: 76c2a1d4aeb7
Create Date: 2026-02-25 23:44:20.628918

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '96e87b774682'
down_revision: Union[str, None] = '76c2a1d4aeb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Seed default assets
    op.execute(
        "INSERT INTO assets (symbol, name, is_fiat, coingecko_id, decimals) VALUES "
        "('USD', 'US Dollar', 1, NULL, 2), "
        "('BTC', 'Bitcoin', 0, 'bitcoin', 8), "
        "('ETH', 'Ethereum', 0, 'ethereum', 18), "
        "('STETH', 'Lido Staked ETH', 0, 'staked-ether', 18), "
        "('SOL', 'Solana', 0, 'solana', 9), "
        "('ATOM', 'Cosmos', 0, 'cosmos', 6)"
    )

    # Seed default settings
    op.execute(
        "INSERT INTO settings (key, value) VALUES "
        "('default_cost_basis_method', 'fifo'), "
        "('tax_year', '2025'), "
        "('base_currency', 'USD'), "
        "('long_term_threshold_days', '365')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key IN "
               "('default_cost_basis_method', 'tax_year', 'base_currency', 'long_term_threshold_days')")
    op.execute("DELETE FROM assets WHERE symbol IN ('USD', 'BTC', 'ETH', 'STETH', 'SOL', 'ATOM')")
