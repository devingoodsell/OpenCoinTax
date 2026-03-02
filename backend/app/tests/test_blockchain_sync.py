"""Tests for the blockchain sync orchestrator (account-level)."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from app.models.account import Account
from app.models.asset import Asset
from app.models.transaction import Transaction
from app.models.wallet import Wallet
from app.services.blockchain_sync import sync_account, is_sync_in_progress, _sync_in_progress, _sync_locks
from app.services.blockchain.base import RawTransaction


@pytest.fixture
def btc_wallet(db):
    w = Wallet(name="BTC Wallet", type="hardware", category="wallet")
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@pytest.fixture
def btc_account(db, btc_wallet):
    a = Account(
        wallet_id=btc_wallet.id,
        name="BTC Account",
        blockchain="bitcoin",
        address="bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@pytest.fixture
def eth_wallet(db):
    w = Wallet(name="ETH Wallet", type="software", category="wallet")
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@pytest.fixture
def eth_account(db, eth_wallet):
    a = Account(
        wallet_id=eth_wallet.id,
        name="ETH Account",
        blockchain="ethereum",
        address="0x742d35cc6634c0532925a3b844bc9e7595f2bd58",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@pytest.fixture
def mock_raw_txs():
    return [
        RawTransaction(
            tx_hash="txhash1",
            datetime_utc=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            from_address="sender123",
            to_address="bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",
            amount=Decimal("0.5"),
            fee=Decimal("0.0001"),
            asset_symbol="BTC",
            asset_name="Bitcoin",
            raw_data={"test": True},
        ),
        RawTransaction(
            tx_hash="txhash2",
            datetime_utc=datetime(2024, 1, 16, 12, 0, 0, tzinfo=timezone.utc),
            from_address="bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",
            to_address="recipient456",
            amount=Decimal("0.2"),
            fee=Decimal("0.0002"),
            asset_symbol="BTC",
            asset_name="Bitcoin",
            raw_data={"test": True},
        ),
    ]


class TestSyncAccount:
    @pytest.mark.asyncio
    async def test_sync_imports_transactions(self, db, btc_wallet, btc_account, mock_raw_txs):
        with patch("app.services.blockchain_sync.ADAPTERS") as mock_adapters:
            mock_adapter = MagicMock()
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.fetch_transactions = AsyncMock(return_value=mock_raw_txs)
            mock_adapter_instance.native_asset_symbol = "BTC"
            mock_adapter_instance.native_asset_name = "Bitcoin"
            mock_adapter.return_value = mock_adapter_instance
            mock_adapters.__contains__ = lambda self, key: key == "bitcoin"
            mock_adapters.__getitem__ = lambda self, key: mock_adapter

            result = await sync_account(db, btc_account)

        assert result["imported"] == 2
        assert result["skipped"] == 0
        assert result["errors"] == 0

        # Check transactions were created
        txs = db.query(Transaction).filter(Transaction.source == "blockchain_sync").all()
        assert len(txs) == 2

        # Check deposit (incoming) — both wallet and account refs set
        deposit = [t for t in txs if t.type == "deposit"][0]
        assert deposit.to_wallet_id == btc_wallet.id
        assert deposit.to_account_id == btc_account.id
        assert deposit.to_amount == "0.5"
        assert deposit.tx_hash == "txhash1"

        # Check withdrawal (outgoing) — both wallet and account refs set
        withdrawal = [t for t in txs if t.type == "withdrawal"][0]
        assert withdrawal.from_wallet_id == btc_wallet.id
        assert withdrawal.from_account_id == btc_account.id
        assert withdrawal.from_amount == "0.2"
        assert withdrawal.fee_amount == "0.0002"

    @pytest.mark.asyncio
    async def test_sync_deduplicates(self, db, btc_account, mock_raw_txs):
        """Second sync should skip already-imported transactions."""
        with patch("app.services.blockchain_sync.ADAPTERS") as mock_adapters:
            mock_adapter = MagicMock()
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.fetch_transactions = AsyncMock(return_value=mock_raw_txs)
            mock_adapter_instance.native_asset_symbol = "BTC"
            mock_adapter_instance.native_asset_name = "Bitcoin"
            mock_adapter.return_value = mock_adapter_instance
            mock_adapters.__contains__ = lambda self, key: key == "bitcoin"
            mock_adapters.__getitem__ = lambda self, key: mock_adapter

            result1 = await sync_account(db, btc_account)
            assert result1["imported"] == 2

            # Reset lock state for second sync
            _sync_in_progress.discard(btc_account.id)
            if btc_account.id in _sync_locks:
                del _sync_locks[btc_account.id]

            result2 = await sync_account(db, btc_account)
            assert result2["imported"] == 0
            assert result2["skipped"] == 2

    @pytest.mark.asyncio
    async def test_sync_updates_account_last_synced_at(self, db, btc_account, mock_raw_txs):
        assert btc_account.last_synced_at is None

        with patch("app.services.blockchain_sync.ADAPTERS") as mock_adapters:
            mock_adapter = MagicMock()
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.fetch_transactions = AsyncMock(return_value=mock_raw_txs)
            mock_adapter_instance.native_asset_symbol = "BTC"
            mock_adapter_instance.native_asset_name = "Bitcoin"
            mock_adapter.return_value = mock_adapter_instance
            mock_adapters.__contains__ = lambda self, key: key == "bitcoin"
            mock_adapters.__getitem__ = lambda self, key: mock_adapter

            await sync_account(db, btc_account)

        db.refresh(btc_account)
        assert btc_account.last_synced_at is not None

    @pytest.mark.asyncio
    async def test_sync_creates_asset_if_missing(self, db, btc_account, mock_raw_txs):
        assert db.query(Asset).filter(Asset.symbol == "BTC").first() is None

        with patch("app.services.blockchain_sync.ADAPTERS") as mock_adapters:
            mock_adapter = MagicMock()
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.fetch_transactions = AsyncMock(return_value=mock_raw_txs)
            mock_adapter_instance.native_asset_symbol = "BTC"
            mock_adapter_instance.native_asset_name = "Bitcoin"
            mock_adapter.return_value = mock_adapter_instance
            mock_adapters.__contains__ = lambda self, key: key == "bitcoin"
            mock_adapters.__getitem__ = lambda self, key: mock_adapter

            await sync_account(db, btc_account)

        btc_asset = db.query(Asset).filter(Asset.symbol == "BTC").first()
        assert btc_asset is not None
        assert btc_asset.name == "Bitcoin"
        assert btc_asset.is_fiat is False

    @pytest.mark.asyncio
    async def test_sync_reuses_existing_asset(self, db, btc_account, mock_raw_txs, seed_assets):
        existing_btc = seed_assets["BTC"]

        with patch("app.services.blockchain_sync.ADAPTERS") as mock_adapters:
            mock_adapter = MagicMock()
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.fetch_transactions = AsyncMock(return_value=mock_raw_txs)
            mock_adapter_instance.native_asset_symbol = "BTC"
            mock_adapter_instance.native_asset_name = "Bitcoin"
            mock_adapter.return_value = mock_adapter_instance
            mock_adapters.__contains__ = lambda self, key: key == "bitcoin"
            mock_adapters.__getitem__ = lambda self, key: mock_adapter

            await sync_account(db, btc_account)

        txs = db.query(Transaction).filter(Transaction.source == "blockchain_sync").all()
        for tx in txs:
            asset_id = tx.to_asset_id or tx.from_asset_id
            assert asset_id == existing_btc.id


class TestSyncValidation:
    @pytest.mark.asyncio
    async def test_rejects_account_without_address(self, db):
        wallet = Wallet(name="No Address", type="hardware", category="wallet")
        db.add(wallet)
        db.commit()
        account = Account(wallet_id=wallet.id, name="Empty", address="", blockchain="")
        db.add(account)
        db.commit()
        db.refresh(account)

        with pytest.raises(ValueError, match="address and blockchain"):
            await sync_account(db, account)

    @pytest.mark.asyncio
    async def test_rejects_unsupported_chain(self, db):
        wallet = Wallet(name="Doge Wallet", type="software", category="wallet")
        db.add(wallet)
        db.commit()
        account = Account(
            wallet_id=wallet.id, name="Doge",
            blockchain="dogecoin", address="DH5yaie",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        with pytest.raises(ValueError, match="Unsupported"):
            await sync_account(db, account)

    @pytest.mark.asyncio
    async def test_rejects_invalid_address(self, db):
        wallet = Wallet(name="Bad ETH Wallet", type="software", category="wallet")
        db.add(wallet)
        db.commit()
        account = Account(
            wallet_id=wallet.id, name="Bad ETH",
            blockchain="ethereum", address="not-an-eth-address",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        with pytest.raises(ValueError, match="Invalid address"):
            await sync_account(db, account)


class TestStakingRewardMapping:
    @pytest.mark.asyncio
    async def test_staking_reward_type(self, db, btc_wallet, btc_account):
        staking_tx = RawTransaction(
            tx_hash="staking1",
            datetime_utc=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            from_address=None,
            to_address=btc_account.address,
            amount=Decimal("0.01"),
            fee=Decimal("0"),
            asset_symbol="BTC",
            asset_name="Bitcoin",
            tx_type="staking_reward",
            raw_data={},
        )

        with patch("app.services.blockchain_sync.ADAPTERS") as mock_adapters:
            mock_adapter = MagicMock()
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.fetch_transactions = AsyncMock(return_value=[staking_tx])
            mock_adapter_instance.native_asset_symbol = "BTC"
            mock_adapter_instance.native_asset_name = "Bitcoin"
            mock_adapter.return_value = mock_adapter_instance
            mock_adapters.__contains__ = lambda self, key: key == "bitcoin"
            mock_adapters.__getitem__ = lambda self, key: mock_adapter

            result = await sync_account(db, btc_account)

        assert result["imported"] == 1
        tx = db.query(Transaction).filter(Transaction.tx_hash == "staking1").first()
        assert tx.type == "staking_reward"
        assert tx.to_wallet_id == btc_wallet.id
        assert tx.to_account_id == btc_account.id


class TestSyncStatus:
    def test_not_in_progress_initially(self, btc_account):
        _sync_in_progress.discard(btc_account.id)
        assert is_sync_in_progress(btc_account.id) is False
