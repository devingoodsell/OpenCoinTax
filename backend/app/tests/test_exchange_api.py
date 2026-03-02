"""Tests for exchange API endpoints (connection CRUD and sync)."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch, AsyncMock

import pytest

from app.models import Wallet, Asset, Transaction
from app.models.exchange_connection import ExchangeConnection
from app.services.blockchain.base import RawTransaction
from app.services.encryption import encrypt, reset_fernet


@pytest.fixture(autouse=True)
def _clean_encryption(monkeypatch, tmp_path):
    """Use temp dir for encryption key file."""
    reset_fernet()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CRYPTO_TAX_ENCRYPTION_KEY", raising=False)
    yield
    reset_fernet()


@pytest.fixture
def exchange_wallet(db) -> Wallet:
    """Create an exchange-category wallet."""
    w = Wallet(name="Coinbase", type="exchange", provider="coinbase", category="exchange")
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@pytest.fixture
def wallet_wallet(db) -> Wallet:
    """Create a wallet-category wallet."""
    w = Wallet(name="Ledger", type="hardware", provider="ledger", category="wallet")
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@pytest.fixture
def btc_asset(db) -> Asset:
    a = Asset(symbol="BTC", name="Bitcoin", is_fiat=False)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ─── Exchange Connection CRUD ───────────────────────────────


def test_create_exchange_connection(client, exchange_wallet):
    resp = client.post(
        f"/api/wallets/{exchange_wallet.id}/exchange-connection",
        json={
            "exchange_type": "coinbase",
            "api_key": "my-api-key",
            "api_secret": "my-api-secret",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["wallet_id"] == exchange_wallet.id
    assert data["exchange_type"] == "coinbase"
    assert data["last_synced_at"] is None
    assert "api_key" not in data  # Should not expose raw key
    assert "api_secret" not in data


def test_create_exchange_connection_wallet_not_exchange(client, wallet_wallet):
    """Wallet-category wallets should not accept exchange connections."""
    resp = client.post(
        f"/api/wallets/{wallet_wallet.id}/exchange-connection",
        json={
            "exchange_type": "coinbase",
            "api_key": "key",
            "api_secret": "secret",
        },
    )
    assert resp.status_code == 400
    assert "only be added to exchanges" in resp.json()["detail"].lower()


def test_create_exchange_connection_wallet_not_found(client):
    resp = client.post(
        "/api/wallets/999/exchange-connection",
        json={
            "exchange_type": "coinbase",
            "api_key": "key",
            "api_secret": "secret",
        },
    )
    assert resp.status_code == 404


def test_create_exchange_connection_update_existing(client, exchange_wallet):
    """Creating a connection when one exists should update it."""
    # Create first
    resp1 = client.post(
        f"/api/wallets/{exchange_wallet.id}/exchange-connection",
        json={
            "exchange_type": "coinbase",
            "api_key": "old-key",
            "api_secret": "old-secret",
        },
    )
    assert resp1.status_code == 201
    conn_id = resp1.json()["id"]

    # Create again — should update
    resp2 = client.post(
        f"/api/wallets/{exchange_wallet.id}/exchange-connection",
        json={
            "exchange_type": "coinbase",
            "api_key": "new-key",
            "api_secret": "new-secret",
        },
    )
    assert resp2.status_code == 201
    assert resp2.json()["id"] == conn_id  # Same record


def test_delete_exchange_connection(client, db, exchange_wallet):
    # Create connection first
    conn = ExchangeConnection(
        wallet_id=exchange_wallet.id,
        exchange_type="coinbase",
        api_key_encrypted=encrypt("key"),
        api_secret_encrypted=encrypt("secret"),
    )
    db.add(conn)
    db.commit()

    resp = client.delete(f"/api/wallets/{exchange_wallet.id}/exchange-connection")
    assert resp.status_code == 200
    assert "deleted" in resp.json()["detail"].lower()


def test_delete_exchange_connection_not_found(client, exchange_wallet):
    resp = client.delete(f"/api/wallets/{exchange_wallet.id}/exchange-connection")
    assert resp.status_code == 404


def test_delete_exchange_connection_wallet_not_found(client):
    resp = client.delete("/api/wallets/999/exchange-connection")
    assert resp.status_code == 404


# ─── Exchange Sync ──────────────────────────────────────────


def _mock_raw_txs():
    """Return a list of mock RawTransaction objects."""
    return [
        RawTransaction(
            tx_hash="coinbase_tx-1",
            datetime_utc=datetime(2024, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
            from_address=None,
            to_address=None,
            amount=Decimal("0.5"),
            fee=Decimal("0"),
            asset_symbol="BTC",
            asset_name="Bitcoin",
            tx_type="buy",
            raw_data={"id": "tx-1", "type": "buy"},
        ),
        RawTransaction(
            tx_hash="coinbase_tx-2",
            datetime_utc=datetime(2024, 7, 2, 12, 0, 0, tzinfo=timezone.utc),
            from_address=None,
            to_address="0xabc",
            amount=Decimal("1.0"),
            fee=Decimal("0.0001"),
            asset_symbol="BTC",
            asset_name="Bitcoin",
            tx_type="withdrawal",
            raw_data={"id": "tx-2", "type": "send"},
        ),
    ]


def test_exchange_sync_success(client, db, exchange_wallet):
    """Sync should import transactions from the exchange adapter."""
    conn = ExchangeConnection(
        wallet_id=exchange_wallet.id,
        exchange_type="coinbase",
        api_key_encrypted=encrypt("key"),
        api_secret_encrypted=encrypt("secret"),
    )
    db.add(conn)
    db.commit()

    mock_adapter = AsyncMock()
    mock_adapter.fetch_transactions = AsyncMock(return_value=_mock_raw_txs())

    with patch("app.api.exchanges.EXCHANGE_ADAPTERS", {"coinbase": lambda **kw: mock_adapter}):
        resp = client.post(f"/api/wallets/{exchange_wallet.id}/exchange-sync")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["imported"] == 2
    assert data["skipped"] == 0
    assert data["errors"] == 0


def test_exchange_sync_deduplication(client, db, exchange_wallet, btc_asset):
    """Already-imported transactions should be skipped."""
    conn = ExchangeConnection(
        wallet_id=exchange_wallet.id,
        exchange_type="coinbase",
        api_key_encrypted=encrypt("key"),
        api_secret_encrypted=encrypt("secret"),
    )
    db.add(conn)
    db.commit()

    # Pre-insert a transaction with same tx_hash
    existing_tx = Transaction(
        tx_hash="coinbase_tx-1",
        datetime_utc=datetime(2024, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
        type="buy",
        source="exchange_sync",
        to_wallet_id=exchange_wallet.id,
        to_amount="0.5",
        to_asset_id=btc_asset.id,
    )
    db.add(existing_tx)
    db.commit()

    mock_adapter = AsyncMock()
    mock_adapter.fetch_transactions = AsyncMock(return_value=_mock_raw_txs())

    with patch("app.api.exchanges.EXCHANGE_ADAPTERS", {"coinbase": lambda **kw: mock_adapter}):
        resp = client.post(f"/api/wallets/{exchange_wallet.id}/exchange-sync")

    data = resp.json()
    assert data["imported"] == 1  # only tx-2
    assert data["skipped"] == 1  # tx-1 already existed


def test_exchange_sync_not_exchange(client, wallet_wallet):
    """Sync on a wallet-category wallet should fail."""
    resp = client.post(f"/api/wallets/{wallet_wallet.id}/exchange-sync")
    assert resp.status_code == 400
    assert "only exchanges" in resp.json()["detail"].lower()


def test_exchange_sync_no_connection(client, exchange_wallet):
    """Sync without a configured connection should fail."""
    resp = client.post(f"/api/wallets/{exchange_wallet.id}/exchange-sync")
    assert resp.status_code == 400
    assert "no api connection" in resp.json()["detail"].lower()


def test_exchange_sync_unsupported_type(client, db, exchange_wallet):
    """Unsupported exchange type should return 400."""
    conn = ExchangeConnection(
        wallet_id=exchange_wallet.id,
        exchange_type="unsupported_exchange",
        api_key_encrypted=encrypt("key"),
        api_secret_encrypted=encrypt("secret"),
    )
    db.add(conn)
    db.commit()

    resp = client.post(f"/api/wallets/{exchange_wallet.id}/exchange-sync")
    assert resp.status_code == 400
    assert "unsupported exchange type" in resp.json()["detail"].lower()


def test_exchange_sync_wallet_not_found(client):
    resp = client.post("/api/wallets/999/exchange-sync")
    assert resp.status_code == 404


def test_exchange_sync_sets_wallet_ids(client, db, exchange_wallet):
    """Buy transactions should set to_wallet_id, withdrawal should set from_wallet_id."""
    conn = ExchangeConnection(
        wallet_id=exchange_wallet.id,
        exchange_type="coinbase",
        api_key_encrypted=encrypt("key"),
        api_secret_encrypted=encrypt("secret"),
    )
    db.add(conn)
    db.commit()

    mock_adapter = AsyncMock()
    mock_adapter.fetch_transactions = AsyncMock(return_value=_mock_raw_txs())

    with patch("app.api.exchanges.EXCHANGE_ADAPTERS", {"coinbase": lambda **kw: mock_adapter}):
        resp = client.post(f"/api/wallets/{exchange_wallet.id}/exchange-sync")

    assert resp.status_code == 200

    # Check that transactions were created correctly
    txs = db.query(Transaction).filter(Transaction.source == "exchange_sync").all()
    buy_tx = next(t for t in txs if t.type == "buy")
    assert buy_tx.to_wallet_id == exchange_wallet.id
    assert buy_tx.from_wallet_id is None

    withdrawal_tx = next(t for t in txs if t.type == "withdrawal")
    assert withdrawal_tx.from_wallet_id == exchange_wallet.id
    assert withdrawal_tx.to_wallet_id is None
