"""Shared test fixtures — in-memory SQLite, sample wallets/assets/transactions."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    Asset, Wallet, Transaction, Setting,
    TransactionType, WalletType, CostBasisMethod,
)


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    """In-memory SQLite engine shared across all connections via StaticPool."""
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(engine):
    """FastAPI test client wired to in-memory DB."""
    SessionLocal = sessionmaker(bind=engine)

    def _override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_assets(db) -> dict[str, Asset]:
    """Create the standard set of assets. Returns {symbol: Asset}."""
    assets_data = [
        ("USD", "US Dollar", True, None, 2),
        ("BTC", "Bitcoin", False, "bitcoin", 8),
        ("ETH", "Ethereum", False, "ethereum", 18),
        ("STETH", "Lido Staked ETH", False, "staked-ether", 18),
        ("SOL", "Solana", False, "solana", 9),
        ("ATOM", "Cosmos", False, "cosmos", 6),
    ]
    result = {}
    for symbol, name, is_fiat, cg_id, decimals in assets_data:
        a = Asset(
            symbol=symbol, name=name, is_fiat=is_fiat,
            coingecko_id=cg_id, decimals=decimals,
        )
        db.add(a)
        result[symbol] = a
    db.commit()
    for a in result.values():
        db.refresh(a)
    return result


@pytest.fixture
def seed_wallets(db) -> dict[str, Wallet]:
    """Create 4 wallets matching the user's setup. Returns {name: Wallet}."""
    wallets_data = [
        ("Coinbase", "exchange", "coinbase", "exchange"),
        ("River", "exchange", "river", "exchange"),
        ("Ledger", "hardware", "ledger", "wallet"),
        ("Trezor", "hardware", "trezor", "wallet"),
    ]
    result = {}
    for name, wtype, provider, category in wallets_data:
        w = Wallet(name=name, type=wtype, provider=provider, category=category)
        db.add(w)
        result[name] = w
    db.commit()
    for w in result.values():
        db.refresh(w)
    return result


@pytest.fixture
def seed_settings(db):
    """Insert default settings."""
    defaults = [
        ("default_cost_basis_method", "fifo"),
        ("tax_year", "2025"),
        ("base_currency", "USD"),
        ("long_term_threshold_days", "365"),
    ]
    for key, value in defaults:
        db.add(Setting(key=key, value=value))
    db.commit()


def make_transaction(
    db: Session,
    *,
    datetime_utc: datetime,
    tx_type: str,
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
    """Helper to create a transaction — avoids repeating boilerplate in tests."""
    tx = Transaction(
        datetime_utc=datetime_utc,
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
    db.commit()
    db.refresh(tx)
    return tx
