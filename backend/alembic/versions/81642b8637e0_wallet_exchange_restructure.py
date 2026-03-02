"""wallet_exchange_restructure

Revision ID: 81642b8637e0
Revises: 43fe402a112b
Create Date: 2026-02-28 10:47:20.926733

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '81642b8637e0'
down_revision: Union[str, None] = '43fe402a112b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Create accounts table
    op.create_table('accounts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('wallet_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('blockchain', sa.String(length=100), nullable=False),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Step 2: Add category and is_archived to wallets (with server defaults for existing rows)
    with op.batch_alter_table('wallets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', sa.String(length=50), nullable=False, server_default='wallet'))
        batch_op.add_column(sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('0')))

    # Step 3: Add account FK columns to transactions
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('from_account_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('to_account_id', sa.Integer(), nullable=True))
        batch_op.create_index('idx_transactions_account', ['from_account_id'], unique=False)
        batch_op.create_index('idx_transactions_to_account', ['to_account_id'], unique=False)
        batch_op.create_foreign_key('fk_transactions_from_account', 'accounts', ['from_account_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_transactions_to_account', 'accounts', ['to_account_id'], ['id'], ondelete='SET NULL')

    # Step 4: Data migration — create accounts from wallets with addresses
    conn = op.get_bind()

    # Set category based on type for all existing wallets
    conn.execute(sa.text(
        "UPDATE wallets SET category = CASE WHEN type = 'exchange' THEN 'exchange' ELSE 'wallet' END"
    ))

    # Create accounts for wallets that have address and blockchain
    wallets_with_addresses = conn.execute(sa.text(
        "SELECT id, address, blockchain, last_synced_at FROM wallets WHERE address IS NOT NULL AND blockchain IS NOT NULL"
    )).fetchall()

    for wallet_row in wallets_with_addresses:
        wallet_id = wallet_row[0]
        address = wallet_row[1]
        blockchain = wallet_row[2]
        last_synced_at = wallet_row[3]
        account_name = f"{blockchain} Account"

        # Insert the account
        result = conn.execute(sa.text(
            "INSERT INTO accounts (wallet_id, name, address, blockchain, last_synced_at, is_archived, created_at, updated_at) "
            "VALUES (:wallet_id, :name, :address, :blockchain, :last_synced_at, 0, datetime('now'), datetime('now'))"
        ), {
            "wallet_id": wallet_id,
            "name": account_name,
            "address": address,
            "blockchain": blockchain,
            "last_synced_at": last_synced_at,
        })
        account_id = result.lastrowid

        # Update transactions that reference this wallet to also reference the new account
        conn.execute(sa.text(
            "UPDATE transactions SET from_account_id = :account_id WHERE from_wallet_id = :wallet_id"
        ), {"account_id": account_id, "wallet_id": wallet_id})
        conn.execute(sa.text(
            "UPDATE transactions SET to_account_id = :account_id WHERE to_wallet_id = :wallet_id"
        ), {"account_id": account_id, "wallet_id": wallet_id})

    # Step 5: Drop old columns from wallets
    with op.batch_alter_table('wallets', schema=None) as batch_op:
        batch_op.drop_column('last_synced_at')
        batch_op.drop_column('koinly_wallet_id')
        batch_op.drop_column('blockchain')
        batch_op.drop_column('address')


def downgrade() -> None:
    # Step 1: Re-add columns to wallets
    with op.batch_alter_table('wallets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('address', sa.TEXT(), nullable=True))
        batch_op.add_column(sa.Column('blockchain', sa.VARCHAR(length=100), nullable=True))
        batch_op.add_column(sa.Column('koinly_wallet_id', sa.VARCHAR(length=255), nullable=True))
        batch_op.add_column(sa.Column('last_synced_at', sa.DATETIME(), nullable=True))

    # Step 2: Migrate data back from accounts to wallets
    conn = op.get_bind()
    accounts = conn.execute(sa.text(
        "SELECT wallet_id, address, blockchain, last_synced_at FROM accounts"
    )).fetchall()
    for acct in accounts:
        conn.execute(sa.text(
            "UPDATE wallets SET address = :address, blockchain = :blockchain, last_synced_at = :last_synced_at WHERE id = :wallet_id"
        ), {"address": acct[1], "blockchain": acct[2], "last_synced_at": acct[3], "wallet_id": acct[0]})

    # Step 3: Drop new columns from wallets
    with op.batch_alter_table('wallets', schema=None) as batch_op:
        batch_op.drop_column('is_archived')
        batch_op.drop_column('category')

    # Step 4: Drop account FK columns from transactions
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_transactions_to_account', type_='foreignkey')
        batch_op.drop_constraint('fk_transactions_from_account', type_='foreignkey')
        batch_op.drop_index('idx_transactions_to_account')
        batch_op.drop_index('idx_transactions_account')
        batch_op.drop_column('to_account_id')
        batch_op.drop_column('from_account_id')

    # Step 5: Drop accounts table
    op.drop_table('accounts')
