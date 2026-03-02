"""Test factories — convenience helpers for creating test entities."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Asset, Wallet, Transaction, Account, TaxLot


def create_asset(
    db: Session,
    *,
    symbol: str = "BTC",
    name: str | None = None,
    is_fiat: bool = False,
    coingecko_id: str | None = None,
    decimals: int = 8,
) -> Asset:
    """Create an asset. Returns the flushed (id-assigned) Asset."""
    asset = Asset(
        symbol=symbol,
        name=name or symbol,
        is_fiat=is_fiat,
        coingecko_id=coingecko_id,
        decimals=decimals,
    )
    db.add(asset)
    db.flush()
    return asset


def create_wallet(
    db: Session,
    *,
    name: str = "Test Wallet",
    type: str = "exchange",
    provider: str | None = None,
    category: str = "exchange",
) -> Wallet:
    """Create a wallet. Returns the flushed (id-assigned) Wallet."""
    wallet = Wallet(
        name=name,
        type=type,
        provider=provider,
        category=category,
    )
    db.add(wallet)
    db.flush()
    return wallet


def create_account(
    db: Session,
    *,
    wallet_id: int,
    name: str = "Test Account",
    address: str = "0x1234",
    blockchain: str = "ethereum",
) -> Account:
    """Create an account. Returns the flushed (id-assigned) Account."""
    account = Account(
        wallet_id=wallet_id,
        name=name,
        address=address,
        blockchain=blockchain,
    )
    db.add(account)
    db.flush()
    return account


def create_transaction(
    db: Session,
    *,
    datetime_utc: datetime | None = None,
    tx_type: str = "buy",
    from_wallet_id: int | None = None,
    to_wallet_id: int | None = None,
    from_amount: str | None = None,
    from_asset_id: int | None = None,
    to_amount: str | None = None,
    to_asset_id: int | None = None,
    fee_amount: str | None = None,
    fee_asset_id: int | None = None,
    fee_value_usd: str | None = None,
    from_value_usd: str | None = None,
    to_value_usd: str | None = None,
    net_value_usd: str | None = None,
    label: str | None = None,
    description: str | None = None,
    tx_hash: str | None = None,
    source: str = "manual",
) -> Transaction:
    """Create a transaction. Returns the flushed (id-assigned) Transaction."""
    tx = Transaction(
        datetime_utc=datetime_utc or datetime(2025, 1, 1, tzinfo=timezone.utc),
        type=tx_type,
        from_wallet_id=from_wallet_id,
        to_wallet_id=to_wallet_id,
        from_amount=from_amount,
        from_asset_id=from_asset_id,
        to_amount=to_amount,
        to_asset_id=to_asset_id,
        fee_amount=fee_amount,
        fee_asset_id=fee_asset_id,
        fee_value_usd=fee_value_usd,
        from_value_usd=from_value_usd,
        to_value_usd=to_value_usd,
        net_value_usd=net_value_usd,
        label=label,
        description=description,
        tx_hash=tx_hash,
        source=source,
    )
    db.add(tx)
    db.flush()
    return tx


def create_tax_lot(
    db: Session,
    *,
    wallet_id: int,
    asset_id: int,
    amount: str = "1.0",
    cost_basis_usd: str = "100.00",
    acquired_date: datetime | None = None,
    acquisition_tx_id: int | None = None,
    source_type: str = "purchase",
) -> TaxLot:
    """Create a tax lot. Returns the flushed (id-assigned) TaxLot."""
    lot = TaxLot(
        wallet_id=wallet_id,
        asset_id=asset_id,
        amount=amount,
        remaining_amount=amount,
        cost_basis_usd=cost_basis_usd,
        cost_basis_per_unit=str(Decimal(cost_basis_usd) / Decimal(amount)),
        acquired_date=acquired_date or datetime(2025, 1, 1, tzinfo=timezone.utc),
        acquisition_tx_id=acquisition_tx_id,
        source_type=source_type,
    )
    db.add(lot)
    db.flush()
    return lot
