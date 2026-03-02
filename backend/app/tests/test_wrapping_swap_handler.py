"""Tests for wrapping_swap_handler — non-taxable basis carry-over."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models import TaxLot
from app.services import wrapping_swap_handler
from app.services.wrapping_swap_handler import is_wrapping_swap, process_wrapping_swap
from app.tests.factories import create_asset, create_wallet, create_transaction, create_tax_lot


@pytest.fixture(autouse=True)
def _clear_symbol_cache():
    """Clear the module-level _symbol_cache between tests."""
    wrapping_swap_handler._symbol_cache.clear()
    yield
    wrapping_swap_handler._symbol_cache.clear()


class TestIsWrappingSwap:
    def test_eth_to_weth(self, db):
        """ETH→WETH trade is a wrapping swap."""
        wallet = create_wallet(db, name="Coinbase")
        eth = create_asset(db, symbol="ETH")
        weth = create_asset(db, symbol="WETH")
        db.commit()

        tx = create_transaction(
            db,
            tx_type="trade",
            from_wallet_id=wallet.id,
            to_wallet_id=wallet.id,
            from_asset_id=eth.id,
            to_asset_id=weth.id,
            from_amount="1.0",
            to_amount="1.0",
        )
        db.commit()

        assert is_wrapping_swap(db, tx) is True

    def test_btc_to_wbtc(self, db):
        """BTC→WBTC trade is a wrapping swap."""
        wallet = create_wallet(db, name="Coinbase")
        btc = create_asset(db, symbol="BTC")
        wbtc = create_asset(db, symbol="WBTC")
        db.commit()

        tx = create_transaction(
            db,
            tx_type="trade",
            from_wallet_id=wallet.id,
            to_wallet_id=wallet.id,
            from_asset_id=btc.id,
            to_asset_id=wbtc.id,
            from_amount="1.0",
            to_amount="1.0",
        )
        db.commit()

        assert is_wrapping_swap(db, tx) is True

    def test_eth_to_steth(self, db):
        """ETH→STETH trade is a wrapping swap."""
        wallet = create_wallet(db, name="Ledger")
        eth = create_asset(db, symbol="ETH")
        steth = create_asset(db, symbol="STETH")
        db.commit()

        tx = create_transaction(
            db,
            tx_type="trade",
            from_wallet_id=wallet.id,
            to_wallet_id=wallet.id,
            from_asset_id=eth.id,
            to_asset_id=steth.id,
            from_amount="1.0",
            to_amount="1.0",
        )
        db.commit()

        assert is_wrapping_swap(db, tx) is True

    def test_non_wrapping_trade(self, db):
        """ETH→BTC trade is NOT a wrapping swap."""
        wallet = create_wallet(db, name="Coinbase")
        eth = create_asset(db, symbol="ETH")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        tx = create_transaction(
            db,
            tx_type="trade",
            from_wallet_id=wallet.id,
            to_wallet_id=wallet.id,
            from_asset_id=eth.id,
            to_asset_id=btc.id,
            from_amount="1.0",
            to_amount="0.05",
        )
        db.commit()

        assert is_wrapping_swap(db, tx) is False

    def test_non_trade_type(self, db):
        """A buy transaction is never a wrapping swap."""
        wallet = create_wallet(db, name="Coinbase")
        eth = create_asset(db, symbol="ETH")
        weth = create_asset(db, symbol="WETH")
        db.commit()

        tx = create_transaction(
            db,
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=weth.id,
            to_amount="1.0",
        )
        db.commit()

        assert is_wrapping_swap(db, tx) is False


class TestProcessWrappingSwap:
    def test_basis_carries_over(self, db):
        """ETH→WETH swap carries cost basis to new lot with zero gain."""
        wallet = create_wallet(db, name="Coinbase")
        eth = create_asset(db, symbol="ETH")
        weth = create_asset(db, symbol="WETH")
        db.commit()

        buy_tx = create_transaction(
            db,
            datetime_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=eth.id,
            to_amount="2.0",
            to_value_usd="4000.00",
        )
        db.commit()

        create_tax_lot(
            db,
            wallet_id=wallet.id,
            asset_id=eth.id,
            amount="2.0",
            cost_basis_usd="4000.00",
            acquired_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            acquisition_tx_id=buy_tx.id,
        )
        db.commit()

        wrap_tx = create_transaction(
            db,
            datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
            tx_type="trade",
            from_wallet_id=wallet.id,
            to_wallet_id=wallet.id,
            from_asset_id=eth.id,
            to_asset_id=weth.id,
            from_amount="2.0",
            to_amount="2.0",
        )
        db.commit()

        new_lots = process_wrapping_swap(db, wrap_tx, 2025)

        assert len(new_lots) == 1
        lot = new_lots[0]
        assert lot.asset_id == weth.id
        assert Decimal(lot.cost_basis_usd) == Decimal("4000.00")
        # Acquired date should carry over from original purchase (SQLite strips tz)
        assert lot.acquired_date.replace(tzinfo=None) == datetime(2024, 1, 1)

    def test_wbtc_to_btc_unwrap(self, db):
        """WBTC→BTC unwrap also carries basis (reverse direction)."""
        wallet = create_wallet(db, name="Ledger")
        btc = create_asset(db, symbol="BTC")
        wbtc = create_asset(db, symbol="WBTC")
        db.commit()

        buy_tx = create_transaction(
            db,
            datetime_utc=datetime(2024, 3, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=wbtc.id,
            to_amount="1.0",
            to_value_usd="50000.00",
        )
        db.commit()

        create_tax_lot(
            db,
            wallet_id=wallet.id,
            asset_id=wbtc.id,
            amount="1.0",
            cost_basis_usd="50000.00",
            acquired_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
            acquisition_tx_id=buy_tx.id,
        )
        db.commit()

        unwrap_tx = create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 15, tzinfo=timezone.utc),
            tx_type="trade",
            from_wallet_id=wallet.id,
            to_wallet_id=wallet.id,
            from_asset_id=wbtc.id,
            to_asset_id=btc.id,
            from_amount="1.0",
            to_amount="1.0",
        )
        db.commit()

        new_lots = process_wrapping_swap(db, unwrap_tx, 2025)

        assert len(new_lots) == 1
        lot = new_lots[0]
        assert lot.asset_id == btc.id
        assert Decimal(lot.cost_basis_usd) == Decimal("50000.00")
        assert lot.acquired_date.replace(tzinfo=None) == datetime(2024, 3, 1)

    def test_partial_wrap_multiple_lots(self, db):
        """Wrapping with multiple source lots distributes basis proportionally."""
        wallet = create_wallet(db, name="Coinbase")
        eth = create_asset(db, symbol="ETH")
        weth = create_asset(db, symbol="WETH")
        db.commit()

        # Buy 1 ETH at $2000
        tx1 = create_transaction(
            db,
            datetime_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=eth.id,
            to_amount="1.0",
            to_value_usd="2000.00",
        )
        # Buy 1 ETH at $3000
        tx2 = create_transaction(
            db,
            datetime_utc=datetime(2024, 6, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=eth.id,
            to_amount="1.0",
            to_value_usd="3000.00",
        )
        db.commit()

        create_tax_lot(
            db,
            wallet_id=wallet.id,
            asset_id=eth.id,
            amount="1.0",
            cost_basis_usd="2000.00",
            acquired_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            acquisition_tx_id=tx1.id,
        )
        create_tax_lot(
            db,
            wallet_id=wallet.id,
            asset_id=eth.id,
            amount="1.0",
            cost_basis_usd="3000.00",
            acquired_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            acquisition_tx_id=tx2.id,
        )
        db.commit()

        # Wrap all 2 ETH → 2 WETH
        wrap_tx = create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="trade",
            from_wallet_id=wallet.id,
            to_wallet_id=wallet.id,
            from_asset_id=eth.id,
            to_asset_id=weth.id,
            from_amount="2.0",
            to_amount="2.0",
        )
        db.commit()

        new_lots = process_wrapping_swap(db, wrap_tx, 2025)

        assert len(new_lots) == 2
        total_basis = sum(Decimal(lot.cost_basis_usd) for lot in new_lots)
        assert total_basis == Decimal("5000.00")  # $2000 + $3000

    def test_source_lot_consumed(self, db):
        """After wrapping, the source lot should be fully consumed."""
        wallet = create_wallet(db, name="Coinbase")
        eth = create_asset(db, symbol="ETH")
        weth = create_asset(db, symbol="WETH")
        db.commit()

        buy_tx = create_transaction(
            db,
            datetime_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=eth.id,
            to_amount="1.0",
            to_value_usd="3000.00",
        )
        db.commit()

        source_lot = create_tax_lot(
            db,
            wallet_id=wallet.id,
            asset_id=eth.id,
            amount="1.0",
            cost_basis_usd="3000.00",
            acquired_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            acquisition_tx_id=buy_tx.id,
        )
        db.commit()

        wrap_tx = create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="trade",
            from_wallet_id=wallet.id,
            to_wallet_id=wallet.id,
            from_asset_id=eth.id,
            to_asset_id=weth.id,
            from_amount="1.0",
            to_amount="1.0",
        )
        db.commit()

        process_wrapping_swap(db, wrap_tx, 2025)

        db.refresh(source_lot)
        assert Decimal(source_lot.remaining_amount) == Decimal("0")
        assert source_lot.is_fully_disposed is True


class TestWrappingSwapEdgeCases:
    def test_missing_asset_returns_empty_symbol(self, db):
        """_get_symbol returns '' for non-existent asset_id."""
        from app.services.wrapping_swap_handler import _get_symbol
        result = _get_symbol(db, 99999)
        assert result == ""

    def test_missing_from_asset_id_returns_false(self, db):
        """Trade with no from_asset_id is not a wrapping swap."""
        wallet = create_wallet(db, name="Coinbase")
        weth = create_asset(db, symbol="WETH")
        db.commit()

        tx = create_transaction(
            db,
            tx_type="trade",
            from_wallet_id=wallet.id,
            to_wallet_id=wallet.id,
            to_asset_id=weth.id,
            from_amount="1.0",
            to_amount="1.0",
        )
        db.commit()

        assert is_wrapping_swap(db, tx) is False

    def test_missing_to_asset_id_returns_false(self, db):
        """Trade with no to_asset_id is not a wrapping swap."""
        wallet = create_wallet(db, name="Coinbase")
        eth = create_asset(db, symbol="ETH")
        db.commit()

        tx = create_transaction(
            db,
            tx_type="trade",
            from_wallet_id=wallet.id,
            to_wallet_id=wallet.id,
            from_asset_id=eth.id,
            from_amount="1.0",
            to_amount="1.0",
        )
        db.commit()

        assert is_wrapping_swap(db, tx) is False

    def test_unknown_symbol_returns_false(self, db):
        """Trade where one symbol is not in wrapping pairs returns False."""
        wallet = create_wallet(db, name="Coinbase")
        a = create_asset(db, symbol="UNKNOWN1")
        b = create_asset(db, symbol="UNKNOWN2")
        db.commit()

        tx = create_transaction(
            db,
            tx_type="trade",
            from_wallet_id=wallet.id,
            to_wallet_id=wallet.id,
            from_asset_id=a.id,
            to_asset_id=b.id,
            from_amount="1.0",
            to_amount="1.0",
        )
        db.commit()

        assert is_wrapping_swap(db, tx) is False

    def test_missing_wallet_ids_raises(self, db):
        """process_wrapping_swap raises ValueError when wallet IDs missing."""
        eth = create_asset(db, symbol="ETH")
        weth = create_asset(db, symbol="WETH")
        db.commit()

        tx = create_transaction(
            db,
            tx_type="trade",
            from_asset_id=eth.id,
            to_asset_id=weth.id,
            from_amount="1.0",
            to_amount="1.0",
        )
        db.commit()

        with pytest.raises(ValueError, match="missing wallet or asset IDs"):
            process_wrapping_swap(db, tx, 2025)

    def test_temp_lot_cleanup_unconsumed(self, db):
        """Existing temp lots that haven't been consumed are deleted and recreated."""
        wallet = create_wallet(db, name="Coinbase")
        eth = create_asset(db, symbol="ETH")
        weth = create_asset(db, symbol="WETH")
        db.commit()

        buy_tx = create_transaction(
            db,
            datetime_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=eth.id,
            to_amount="1.0",
            to_value_usd="3000.00",
        )
        db.commit()

        create_tax_lot(
            db,
            wallet_id=wallet.id,
            asset_id=eth.id,
            amount="1.0",
            cost_basis_usd="3000.00",
            acquired_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            acquisition_tx_id=buy_tx.id,
        )

        wrap_tx = create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="trade",
            from_wallet_id=wallet.id,
            to_wallet_id=wallet.id,
            from_asset_id=eth.id,
            to_asset_id=weth.id,
            from_amount="1.0",
            to_amount="1.0",
        )
        db.commit()

        # Create a "temp lot" that would have been created before
        temp_lot = create_tax_lot(
            db,
            wallet_id=wallet.id,
            asset_id=weth.id,
            amount="1.0",
            cost_basis_usd="0.00",
            acquired_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            acquisition_tx_id=wrap_tx.id,
            source_type="wrapping_swap",
        )
        db.commit()
        temp_lot_id = temp_lot.id

        # Process the swap — should delete temp lot and create new one with real basis
        new_lots = process_wrapping_swap(db, wrap_tx, 2025)

        assert len(new_lots) == 1
        # Key: the new lot has real cost basis ($3k), not the temp lot's $0
        assert Decimal(new_lots[0].cost_basis_usd) == Decimal("3000.00")
