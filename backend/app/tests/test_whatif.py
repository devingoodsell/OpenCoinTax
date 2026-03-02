"""Tests for whatif — what-if analysis comparing cost basis methods."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.services.whatif import whatif_analysis
from app.tests.factories import create_asset, create_wallet, create_transaction, create_tax_lot


class TestWhatifAnalysis:
    def test_fifo_vs_lifo_comparison(self, db):
        """FIFO and LIFO should produce different results with different-priced lots."""
        wallet = create_wallet(db, name="Coinbase")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        # Buy 1 BTC at $20,000
        tx1 = create_transaction(
            db,
            datetime_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=btc.id,
            to_amount="1.0",
            to_value_usd="20000.00",
        )
        # Buy 1 BTC at $40,000
        tx2 = create_transaction(
            db,
            datetime_utc=datetime(2024, 6, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=btc.id,
            to_amount="1.0",
            to_value_usd="40000.00",
        )
        db.commit()

        create_tax_lot(db, wallet_id=wallet.id, asset_id=btc.id, amount="1.0",
                       cost_basis_usd="20000.00",
                       acquired_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                       acquisition_tx_id=tx1.id)
        create_tax_lot(db, wallet_id=wallet.id, asset_id=btc.id, amount="1.0",
                       cost_basis_usd="40000.00",
                       acquired_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
                       acquisition_tx_id=tx2.id)
        db.commit()

        # Sell 1 BTC at $50,000
        sell_tx = create_transaction(
            db,
            datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="sell",
            from_wallet_id=wallet.id,
            from_asset_id=btc.id,
            from_amount="1.0",
            from_value_usd="50000.00",
        )
        db.commit()

        result = whatif_analysis(db, sell_tx.id)

        assert result["transaction_id"] == sell_tx.id
        assert result["disposal_amount"] == "1.0"

        # FIFO uses $20k lot → $30k gain
        fifo = result["methods"]["fifo"]
        assert fifo["error"] is None
        assert Decimal(fifo["total_gain_loss"]) == Decimal("30000.00")

        # LIFO uses $40k lot → $10k gain
        lifo = result["methods"]["lifo"]
        assert lifo["error"] is None
        assert Decimal(lifo["total_gain_loss"]) == Decimal("10000.00")

        # HIFO uses $40k lot (highest cost) → $10k gain
        hifo = result["methods"]["hifo"]
        assert hifo["error"] is None
        assert Decimal(hifo["total_gain_loss"]) == Decimal("10000.00")

        # Most tax efficient should be LIFO or HIFO (lowest gain)
        assert result["most_tax_efficient"] in ("lifo", "hifo")

    def test_single_lot(self, db):
        """With a single lot, all methods should produce the same result."""
        wallet = create_wallet(db, name="Ledger")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        tx = create_transaction(
            db,
            datetime_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=btc.id,
            to_amount="2.0",
            to_value_usd="60000.00",
        )
        db.commit()

        create_tax_lot(db, wallet_id=wallet.id, asset_id=btc.id, amount="2.0",
                       cost_basis_usd="60000.00",
                       acquired_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                       acquisition_tx_id=tx.id)
        db.commit()

        sell_tx = create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="sell",
            from_wallet_id=wallet.id,
            from_asset_id=btc.id,
            from_amount="1.0",
            from_value_usd="40000.00",
        )
        db.commit()

        result = whatif_analysis(db, sell_tx.id)

        fifo_gl = Decimal(result["methods"]["fifo"]["total_gain_loss"])
        lifo_gl = Decimal(result["methods"]["lifo"]["total_gain_loss"])
        hifo_gl = Decimal(result["methods"]["hifo"]["total_gain_loss"])

        # All methods give same result with one lot
        assert fifo_gl == lifo_gl == hifo_gl

    def test_nonexistent_transaction_raises(self, db):
        with pytest.raises(ValueError, match="not found"):
            whatif_analysis(db, 99999)

    def test_non_disposal_raises(self, db):
        wallet = create_wallet(db, name="Coinbase")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        # A buy (no from_wallet) should raise
        tx = create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=btc.id,
            to_amount="1.0",
        )
        db.commit()

        with pytest.raises(ValueError, match="not a disposal"):
            whatif_analysis(db, tx.id)
