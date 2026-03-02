"""Tests for multi-wallet transfer handling."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.models import TaxLot, LotAssignment
from app.services.tax_engine import calculate_for_wallet_asset
from app.services.transfer_handler import process_transfer
from app.tests.conftest import make_transaction


class TestSimpleTransfer:
    """Transfer 1 BTC from Coinbase to Ledger — no gain/loss, basis carries over."""

    def test_basis_carries_over(self, db, seed_wallets, seed_assets, seed_settings):
        cb = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        # Buy on Coinbase
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=cb.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        calculate_for_wallet_asset(db, cb.id, btc.id, 2025)

        # Transfer to Ledger
        transfer_tx = make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            from_wallet_id=cb.id, to_wallet_id=ledger.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="1.0", to_asset_id=btc.id,
        )

        new_lots = process_transfer(db, transfer_tx, 2025)
        db.commit()

        assert len(new_lots) == 1
        assert Decimal(new_lots[0].cost_basis_usd) == Decimal("30000.00")
        assert new_lots[0].wallet_id == ledger.id

        # Verify source lot is fully disposed
        source_lot = db.query(TaxLot).filter_by(
            wallet_id=cb.id, asset_id=btc.id
        ).first()
        assert source_lot.is_fully_disposed is True


class TestTransferPreservesAcquiredDate:
    """Original lot from Jan 2024 → transferred lot still shows Jan 2024."""

    def test_date_preserved(self, db, seed_wallets, seed_assets, seed_settings):
        cb = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        buy_date = datetime(2024, 1, 15, tzinfo=timezone.utc)

        make_transaction(
            db, datetime_utc=buy_date,
            tx_type="buy", to_wallet_id=cb.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        calculate_for_wallet_asset(db, cb.id, btc.id, 2024)

        transfer_tx = make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            from_wallet_id=cb.id, to_wallet_id=ledger.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="1.0", to_asset_id=btc.id,
        )

        new_lots = process_transfer(db, transfer_tx, 2025)
        db.commit()

        # Acquired date should be the original buy date, not transfer date
        # SQLite strips tzinfo, so compare without timezone
        assert new_lots[0].acquired_date.replace(tzinfo=None) == buy_date.replace(tzinfo=None)


class TestChainedTransfers:
    """Coinbase → Wallet 1 → Wallet 2. Cost basis must propagate."""

    def test_chain_propagation(self, db, seed_wallets, seed_assets, seed_settings):
        cb = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        trezor = seed_wallets["Trezor"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=cb.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        calculate_for_wallet_asset(db, cb.id, btc.id, 2025)

        # Transfer 1: Coinbase → Ledger
        tx1 = make_transaction(
            db, datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            from_wallet_id=cb.id, to_wallet_id=ledger.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="1.0", to_asset_id=btc.id,
        )
        process_transfer(db, tx1, 2025)
        db.commit()

        # Transfer 2: Ledger → Trezor
        tx2 = make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            from_wallet_id=ledger.id, to_wallet_id=trezor.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="1.0", to_asset_id=btc.id,
        )
        new_lots = process_transfer(db, tx2, 2025)
        db.commit()

        # Final lot should have original $30k basis
        assert Decimal(new_lots[0].cost_basis_usd) == Decimal("30000.00")
        assert new_lots[0].wallet_id == trezor.id


class TestPartialTransfer:
    """Transfer 0.5 of a 2.0 lot → source has 1.5, destination has 0.5."""

    def test_partial(self, db, seed_wallets, seed_assets, seed_settings):
        cb = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=cb.id,
            to_amount="2.0", to_asset_id=btc.id,
            to_value_usd="60000.00",
        )
        calculate_for_wallet_asset(db, cb.id, btc.id, 2025)

        tx = make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            from_wallet_id=cb.id, to_wallet_id=ledger.id,
            from_amount="0.5", from_asset_id=btc.id,
            to_amount="0.5", to_asset_id=btc.id,
        )
        new_lots = process_transfer(db, tx, 2025)
        db.commit()

        # Source lot: 2.0 - 0.5 = 1.5 remaining
        source_lot = db.query(TaxLot).filter_by(
            wallet_id=cb.id, asset_id=btc.id
        ).first()
        assert Decimal(source_lot.remaining_amount) == Decimal("1.5")

        # Destination lot: 0.5 with proportional basis ($15k)
        assert Decimal(new_lots[0].amount) == Decimal("0.5")
        assert Decimal(new_lots[0].cost_basis_usd) == Decimal("15000.00")


class TestTransferThenSell:
    """Transfer to hardware wallet, sell from hardware wallet → correct gain."""

    def test_sell_after_transfer(self, db, seed_wallets, seed_assets, seed_settings):
        cb = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=cb.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        calculate_for_wallet_asset(db, cb.id, btc.id, 2025)

        tx = make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            from_wallet_id=cb.id, to_wallet_id=ledger.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="1.0", to_asset_id=btc.id,
        )
        process_transfer(db, tx, 2025)
        db.commit()

        # Now sell from Ledger
        make_transaction(
            db, datetime_utc=datetime(2025, 9, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=ledger.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="45000.00",
        )

        result = calculate_for_wallet_asset(db, ledger.id, btc.id, 2025)

        # Basis carried over = $30k; Proceeds = $45k; Gain = $15k
        assert result["total_gains"] == "15000.00"


class TestTransferWithFee:
    """Transfer fee adds to carried-over cost basis."""

    def test_fee_increases_basis(self, db, seed_wallets, seed_assets, seed_settings):
        cb = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=cb.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        calculate_for_wallet_asset(db, cb.id, btc.id, 2025)

        tx = make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            from_wallet_id=cb.id, to_wallet_id=ledger.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="1.0", to_asset_id=btc.id,
            fee_amount="0.0001", fee_value_usd="10.00",
        )
        new_lots = process_transfer(db, tx, 2025)
        db.commit()

        # Basis = $30,000 + $10 fee = $30,010
        assert Decimal(new_lots[0].cost_basis_usd) == Decimal("30010.00")


class TestTransferMissingIds:
    """Transfer with missing wallet/asset IDs raises ValueError."""

    def test_missing_from_wallet_id(self, db, seed_wallets, seed_assets, seed_settings):
        ledger = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        tx = make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            to_wallet_id=ledger.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="1.0", to_asset_id=btc.id,
        )

        with pytest.raises(ValueError, match="missing wallet or asset IDs"):
            process_transfer(db, tx, 2025)

    def test_missing_to_wallet_id(self, db, seed_wallets, seed_assets, seed_settings):
        cb = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Buy first so there are lots to consume
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=cb.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        calculate_for_wallet_asset(db, cb.id, btc.id, 2025)

        tx = make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            from_wallet_id=cb.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="1.0", to_asset_id=btc.id,
        )

        with pytest.raises(ValueError, match="missing wallet or asset IDs"):
            process_transfer(db, tx, 2025)

    def test_missing_asset_id(self, db, seed_wallets, seed_assets, seed_settings):
        cb = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]

        tx = make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            from_wallet_id=cb.id, to_wallet_id=ledger.id,
            from_amount="1.0",
            to_amount="1.0",
        )

        with pytest.raises(ValueError, match="missing wallet or asset IDs"):
            process_transfer(db, tx, 2025)


class TestTransferTempLots:
    """Tests for temporary lot handling in transfers."""

    def test_unconsumed_temp_lots_deleted(self, db, seed_wallets, seed_assets, seed_settings):
        """Existing temp lots that haven't been consumed are deleted and recreated."""
        cb = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        # Buy on Coinbase
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=cb.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        calculate_for_wallet_asset(db, cb.id, btc.id, 2025)

        # Create transfer tx
        transfer_tx = make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            from_wallet_id=cb.id, to_wallet_id=ledger.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="1.0", to_asset_id=btc.id,
        )

        # Manually create a temp lot in destination (simulating out-of-order processing)
        temp_lot = TaxLot(
            wallet_id=ledger.id,
            asset_id=btc.id,
            amount="1.0",
            remaining_amount="1.0",
            cost_basis_usd="0.00",
            cost_basis_per_unit="0.00",
            acquired_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
            acquisition_tx_id=transfer_tx.id,
            source_type="transfer_in",
        )
        db.add(temp_lot)
        db.commit()
        temp_lot_id = temp_lot.id

        # Process transfer — should delete temp lot and create new one with real basis
        new_lots = process_transfer(db, transfer_tx, 2025)
        db.commit()

        assert len(new_lots) == 1
        # Key: the new lot has real cost basis ($30k), not the temp lot's $0
        assert Decimal(new_lots[0].cost_basis_usd) == Decimal("30000.00")

    def test_consumed_temp_lots_preserved(self, db, seed_wallets, seed_assets, seed_settings):
        """Temp lots that have been used by disposals are kept."""
        cb = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        # Buy on Coinbase
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=cb.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        calculate_for_wallet_asset(db, cb.id, btc.id, 2025)

        # Create transfer tx
        transfer_tx = make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            from_wallet_id=cb.id, to_wallet_id=ledger.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="1.0", to_asset_id=btc.id,
        )

        # Manually create a temp lot in destination
        temp_lot = TaxLot(
            wallet_id=ledger.id,
            asset_id=btc.id,
            amount="1.0",
            remaining_amount="0.5",  # Partially consumed
            cost_basis_usd="0.00",
            cost_basis_per_unit="0.00",
            acquired_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
            acquisition_tx_id=transfer_tx.id,
            source_type="transfer_in",
        )
        db.add(temp_lot)
        db.commit()

        # Process transfer — consumed temp lots should be preserved
        result_lots = process_transfer(db, transfer_tx, 2025)
        db.commit()

        # The consumed temp lot should be returned
        assert len(result_lots) == 1
        assert result_lots[0].id == temp_lot.id
