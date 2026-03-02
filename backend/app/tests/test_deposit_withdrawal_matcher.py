"""Tests for deposit-withdrawal matching service."""

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Transaction, TaxLot, LotAssignment
from app.services.deposit_withdrawal_matcher import (
    find_deposit_withdrawal_pairs,
    find_duplicate_deposit_withdrawal_pairs,
)
from app.tests.conftest import make_transaction


class TestDepositWithdrawalMatching:
    """Test matching orphan deposits with orphan withdrawals."""

    def test_matches_same_asset_same_amount(self, db, seed_assets, seed_wallets, seed_settings):
        """Deposit and withdrawal of same asset/amount within time window are matched."""
        coinbase = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        # Orphan withdrawal from Coinbase (no to_wallet)
        make_transaction(db, datetime_utc=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                         tx_type="withdrawal", from_wallet_id=coinbase.id,
                         from_amount="0.5", from_asset_id=btc.id,
                         from_value_usd="25000")

        # Orphan deposit into Ledger (no from_wallet)
        make_transaction(db, datetime_utc=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                         tx_type="deposit", to_wallet_id=ledger.id,
                         to_amount="0.5", to_asset_id=btc.id,
                         to_value_usd="25000")

        matches = find_deposit_withdrawal_pairs(db, dry_run=True)
        assert len(matches) == 1
        assert matches[0]["asset"] == "BTC"
        assert matches[0]["deposit_amount"] == "0.5"

    def test_converts_to_transfer_on_apply(self, db, seed_assets, seed_wallets, seed_settings):
        """When dry_run=False, deposit is deleted and withdrawal becomes a transfer."""
        coinbase = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        atom = seed_assets["ATOM"]

        wd = make_transaction(db, datetime_utc=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                              tx_type="withdrawal", from_wallet_id=coinbase.id,
                              from_amount="100", from_asset_id=atom.id,
                              from_value_usd="500")

        dep = make_transaction(db, datetime_utc=datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc),
                               tx_type="deposit", to_wallet_id=ledger.id,
                               to_amount="100", to_asset_id=atom.id,
                               to_value_usd="500")

        matches = find_deposit_withdrawal_pairs(db, dry_run=False)
        assert len(matches) == 1

        # Deposit should be deleted
        assert db.get(Transaction, dep.id) is None

        # Withdrawal should now be a transfer
        tx = db.get(Transaction, wd.id)
        assert tx.type == "transfer"
        assert tx.from_wallet_id == coinbase.id
        assert tx.to_wallet_id == ledger.id
        assert tx.from_amount == "100"
        assert tx.to_amount == "100"

    def test_no_match_different_assets(self, db, seed_assets, seed_wallets, seed_settings):
        """Deposit of BTC and withdrawal of ETH should not match."""
        coinbase = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]

        make_transaction(db, datetime_utc=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                         tx_type="withdrawal", from_wallet_id=coinbase.id,
                         from_amount="1.0", from_asset_id=seed_assets["ETH"].id,
                         from_value_usd="3000")

        make_transaction(db, datetime_utc=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                         tx_type="deposit", to_wallet_id=ledger.id,
                         to_amount="0.1", to_asset_id=seed_assets["BTC"].id,
                         to_value_usd="3000")

        matches = find_deposit_withdrawal_pairs(db, dry_run=True)
        assert len(matches) == 0

    def test_no_match_too_far_apart(self, db, seed_assets, seed_wallets, seed_settings):
        """Deposit and withdrawal >24h apart should not match."""
        coinbase = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        make_transaction(db, datetime_utc=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                         tx_type="withdrawal", from_wallet_id=coinbase.id,
                         from_amount="0.5", from_asset_id=btc.id,
                         from_value_usd="25000")

        make_transaction(db, datetime_utc=datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc),
                         tx_type="deposit", to_wallet_id=ledger.id,
                         to_amount="0.5", to_asset_id=btc.id,
                         to_value_usd="25000")

        matches = find_deposit_withdrawal_pairs(db, dry_run=True)
        assert len(matches) == 0

    def test_no_match_amounts_too_different(self, db, seed_assets, seed_wallets, seed_settings):
        """Deposit and withdrawal amounts >5% different should not match."""
        coinbase = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        make_transaction(db, datetime_utc=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                         tx_type="withdrawal", from_wallet_id=coinbase.id,
                         from_amount="1.0", from_asset_id=btc.id,
                         from_value_usd="50000")

        make_transaction(db, datetime_utc=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                         tx_type="deposit", to_wallet_id=ledger.id,
                         to_amount="0.5", to_asset_id=btc.id,
                         to_value_usd="25000")

        matches = find_deposit_withdrawal_pairs(db, dry_run=True)
        assert len(matches) == 0

    def test_no_match_same_wallet(self, db, seed_assets, seed_wallets, seed_settings):
        """Deposit and withdrawal from/to the same wallet should not match."""
        coinbase = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(db, datetime_utc=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                         tx_type="withdrawal", from_wallet_id=coinbase.id,
                         from_amount="0.5", from_asset_id=btc.id,
                         from_value_usd="25000")

        make_transaction(db, datetime_utc=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                         tx_type="deposit", to_wallet_id=coinbase.id,
                         to_amount="0.5", to_asset_id=btc.id,
                         to_value_usd="25000")

        matches = find_deposit_withdrawal_pairs(db, dry_run=True)
        assert len(matches) == 0


class TestDuplicateDetection:
    """Test finding deposit+withdrawal pairs that duplicate existing transfers."""

    def test_detects_duplicate_pair(self, db, seed_assets, seed_wallets, seed_settings):
        """Deposit+withdrawal that duplicate an existing transfer are detected."""
        coinbase = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        atom = seed_assets["ATOM"]

        # Existing transfer
        make_transaction(db, datetime_utc=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                         tx_type="transfer",
                         from_wallet_id=coinbase.id, to_wallet_id=ledger.id,
                         from_amount="100", to_amount="100",
                         from_asset_id=atom.id, to_asset_id=atom.id,
                         net_value_usd="500")

        # Duplicate deposit into same wallet as transfer from_wallet (self-deposit pattern)
        make_transaction(db, datetime_utc=datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
                         tx_type="deposit", to_wallet_id=coinbase.id,
                         to_amount="100", to_asset_id=atom.id,
                         to_value_usd="500")

        # Duplicate withdrawal from same wallet as transfer from_wallet
        make_transaction(db, datetime_utc=datetime(2024, 1, 1, 11, 30, tzinfo=timezone.utc),
                         tx_type="withdrawal", from_wallet_id=coinbase.id,
                         from_amount="100", from_asset_id=atom.id,
                         from_value_usd="500")

        dupes = find_duplicate_deposit_withdrawal_pairs(db, dry_run=True)
        assert len(dupes) == 1
        assert dupes[0]["asset"] == "ATOM"
        assert dupes[0]["amount"] == "100"

    def test_deletes_duplicates_on_apply(self, db, seed_assets, seed_wallets, seed_settings):
        """Applying deletes the duplicate deposit and withdrawal transactions."""
        coinbase = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        atom = seed_assets["ATOM"]

        xfer = make_transaction(db, datetime_utc=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                                tx_type="transfer",
                                from_wallet_id=coinbase.id, to_wallet_id=ledger.id,
                                from_amount="100", to_amount="100",
                                from_asset_id=atom.id, to_asset_id=atom.id,
                                net_value_usd="500")

        dep = make_transaction(db, datetime_utc=datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
                               tx_type="deposit", to_wallet_id=coinbase.id,
                               to_amount="100", to_asset_id=atom.id,
                               to_value_usd="500")

        wd = make_transaction(db, datetime_utc=datetime(2024, 1, 1, 11, 30, tzinfo=timezone.utc),
                              tx_type="withdrawal", from_wallet_id=coinbase.id,
                              from_amount="100", from_asset_id=atom.id,
                              from_value_usd="500")

        dupes = find_duplicate_deposit_withdrawal_pairs(db, dry_run=False)
        assert len(dupes) == 1

        # Deposit and withdrawal should be deleted
        assert db.get(Transaction, dep.id) is None
        assert db.get(Transaction, wd.id) is None

        # Transfer should still exist
        assert db.get(Transaction, xfer.id) is not None
