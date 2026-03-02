"""Tests for the core tax engine — cost basis calculation pipeline."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.models import TaxLot, LotAssignment, Setting
from app.services.tax_engine import (
    calculate_for_wallet_asset,
    recalculate_for_wallet_asset,
    recalculate_all,
    _holding_period,
)
from app.tests.conftest import make_transaction


class TestSimpleBuyAndSell:
    """Buy 1 BTC at $30k, sell at $40k → $10k gain."""

    def test_basic_gain(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        usd = seed_assets["USD"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 15, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            from_amount="30000.00", from_asset_id=usd.id,
            to_value_usd="30000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 15, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="40000.00", to_asset_id=usd.id,
            from_value_usd="40000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        assert result["total_gains"] == "10000.00"
        assert result["total_losses"] == "0.00"
        assert result["net_gain_loss"] == "10000.00"


class TestFIFOOrdering:
    """Buy 1 BTC at $20k, 1 BTC at $30k, sell 1 BTC at $35k. FIFO uses $20k lot."""

    def test_fifo_uses_oldest(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        usd = seed_assets["USD"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="20000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="35000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025, method="fifo")

        assert result["total_gains"] == "15000.00"  # 35k - 20k
        assert result["total_losses"] == "0.00"


class TestLIFOOrdering:
    """Same setup as FIFO but LIFO uses the $30k lot. Gain = $5k."""

    def test_lifo_uses_newest(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="20000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="35000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025, method="lifo")

        assert result["total_gains"] == "5000.00"  # 35k - 30k


class TestHIFOOrdering:
    """Lots at $20k, $30k, $25k. HIFO uses $30k lot."""

    def test_hifo_uses_highest_cost(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="20000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="25000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 7, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="35000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025, method="hifo")

        assert result["total_gains"] == "5000.00"  # 35k - 30k


class TestPartialLotConsumption:
    """Buy 2 BTC at $30k each. Sell 0.5 BTC at $40k. Lot should have 1.5 remaining."""

    def test_partial_sell(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="2.0", to_asset_id=btc.id,
            to_value_usd="60000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="0.5", from_asset_id=btc.id,
            from_value_usd="20000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        # Gain = 20k - (0.5 * 30k) = 20k - 15k = 5k
        assert result["total_gains"] == "5000.00"

        # Check lot remaining
        lot = db.query(TaxLot).filter_by(wallet_id=w.id, asset_id=btc.id).first()
        assert Decimal(lot.remaining_amount) == Decimal("1.5")


class TestMultiLotConsumption:
    """Sell spans across multiple lots."""

    def test_spans_two_lots(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="20000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.5", from_asset_id=btc.id,
            from_value_usd="52500.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025, method="fifo")

        # FIFO: consume all of lot1 (1.0 @ $20k) + 0.5 of lot2 (0.5 @ $30k)
        # Basis = $20k + $15k = $35k; Proceeds = $52,500; Gain = $17,500
        assert result["total_gains"] == "17500.00"

        # Verify lot assignments
        assignments = db.query(LotAssignment).all()
        assert len(assignments) == 2


class TestFeeHandling:
    def test_buy_fee_increases_basis(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
            fee_amount="50.00", fee_value_usd="50.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="40000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        # Basis = $30,050 (price + fee); Gain = $40k - $30,050 = $9,950
        assert result["total_gains"] == "9950.00"

    def test_sell_fee_reduces_proceeds(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="40000.00",
            fee_amount="50.00", fee_value_usd="50.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        # Proceeds = $40k - $50 fee = $39,950; Gain = $39,950 - $30k = $9,950
        assert result["total_gains"] == "9950.00"


class TestHoldingPeriod:
    def test_long_term(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="40000.00",
        )

        # Need to calculate for both years to create the lot
        calculate_for_wallet_asset(db, w.id, btc.id, 2024)
        calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        assignment = db.query(LotAssignment).filter_by(tax_year=2025).first()
        assert assignment.holding_period == "long_term"

    def test_short_term(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="40000.00",
        )

        calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        assignment = db.query(LotAssignment).first()
        assert assignment.holding_period == "short_term"


class TestLossRealization:
    """Buy at $50k, sell at $30k → $20k loss."""

    def test_loss(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="50000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="30000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        assert result["total_gains"] == "0.00"
        assert result["total_losses"] == "20000.00"
        assert result["net_gain_loss"] == "-20000.00"


class TestZeroCostBasis:
    """Airdrop with $0 FMV, sell later → entire proceeds = gain."""

    def test_airdrop_gain(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="airdrop", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="0.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="500.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        assert result["total_gains"] == "500.00"


class TestPerWalletIsolation:
    """Same asset in two wallets with different methods → independent calculations."""

    def test_independent_wallets(self, db, seed_wallets, seed_assets, seed_settings):
        cb = seed_wallets["Coinbase"]
        rv = seed_wallets["River"]
        btc = seed_assets["BTC"]

        # Coinbase: buy 1 @ $20k, 1 @ $30k
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=cb.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="20000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=cb.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )

        # River: buy 1 @ $25k
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 15, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=rv.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="25000.00",
        )

        # Sell 1 from each
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=cb.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="35000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=rv.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="35000.00",
        )

        cb_result = calculate_for_wallet_asset(db, cb.id, btc.id, 2025, method="fifo")
        rv_result = calculate_for_wallet_asset(db, rv.id, btc.id, 2025, method="fifo")

        # Coinbase FIFO: uses $20k lot → gain = $15k
        assert cb_result["total_gains"] == "15000.00"
        # River FIFO: uses $25k lot → gain = $10k
        assert rv_result["total_gains"] == "10000.00"


class TestStakingIncome:
    """Staking reward creates income event and lot."""

    def test_staking_creates_income_and_lot(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        eth = seed_assets["ETH"]

        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="staking_reward", to_wallet_id=w.id,
            to_amount="0.01", to_asset_id=eth.id,
            to_value_usd="30.00",
        )

        result = calculate_for_wallet_asset(db, w.id, eth.id, 2025)

        assert result["total_income"] == "30.00"

        # Verify lot was created with FMV as cost basis
        lot = db.query(TaxLot).filter_by(wallet_id=w.id, asset_id=eth.id).first()
        assert lot is not None
        assert Decimal(lot.cost_basis_usd) == Decimal("30.00")

    def test_sell_staking_reward(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        eth = seed_assets["ETH"]

        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="staking_reward", to_wallet_id=w.id,
            to_amount="0.01", to_asset_id=eth.id,
            to_value_usd="30.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 9, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="0.01", from_asset_id=eth.id,
            from_value_usd="50.00",
        )

        result = calculate_for_wallet_asset(db, w.id, eth.id, 2025)

        # Income = $30, Capital gain = $50 - $30 = $20
        assert result["total_income"] == "30.00"
        assert result["total_gains"] == "20.00"


class TestRecalculation:
    """Verify recalculation produces identical results."""

    def test_recalculate_is_idempotent(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="40000.00",
        )

        result1 = calculate_for_wallet_asset(db, w.id, btc.id, 2025)
        result2 = recalculate_for_wallet_asset(db, w.id, btc.id, 2025)

        assert result1["total_gains"] == result2["total_gains"]
        assert result1["total_losses"] == result2["total_losses"]
        assert result1["net_gain_loss"] == result2["net_gain_loss"]


class TestNetValueUsdFallback:
    """Verify that net_value_usd is used when per-leg values are NULL (Koinly imports)."""

    def test_buy_with_only_net_value(self, db, seed_wallets, seed_assets, seed_settings):
        """Buy with NULL to_value_usd but net_value_usd='30000' → lot has $30k cost basis."""
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 15, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            net_value_usd="30000.00",
            # to_value_usd intentionally omitted (None)
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        lot = db.query(TaxLot).filter_by(wallet_id=w.id, asset_id=btc.id).first()
        assert lot is not None
        assert Decimal(lot.cost_basis_usd) == Decimal("30000.00")

    def test_sell_with_only_net_value(self, db, seed_wallets, seed_assets, seed_settings):
        """Sell proceeds fall back to net_value_usd → correct gain."""
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Buy with explicit to_value_usd
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        # Sell with only net_value_usd
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            net_value_usd="40000.00",
            # from_value_usd intentionally omitted (None)
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        assert result["total_gains"] == "10000.00"
        assert result["total_losses"] == "0.00"

    def test_transfer_after_net_value_buy(self, db, seed_wallets, seed_assets, seed_settings):
        """Buy with only net_value_usd, then transfer → no InsufficientLotsError, basis carries over."""
        cb = seed_wallets["Coinbase"]
        ledger = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        # Buy with only net_value_usd
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 15, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=cb.id,
            to_amount="1.0", to_asset_id=btc.id,
            net_value_usd="30000.00",
        )

        # Calculate to create the lot from the buy
        calculate_for_wallet_asset(db, cb.id, btc.id, 2025)

        # Transfer from Coinbase to Ledger
        make_transaction(
            db, datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
            tx_type="transfer",
            from_wallet_id=cb.id, from_asset_id=btc.id, from_amount="1.0",
            to_wallet_id=ledger.id, to_asset_id=btc.id, to_amount="1.0",
            net_value_usd="31000.00",
        )

        # Recalculate — should not raise InsufficientLotsError
        from app.services.tax_engine import recalculate_all
        data = recalculate_all(db, tax_year=2025)

        # No errors
        assert data["error_transaction_count"] == 0

        # Ledger should have a lot with the original $30k cost basis
        lot = db.query(TaxLot).filter_by(
            wallet_id=ledger.id, asset_id=btc.id
        ).first()
        assert lot is not None
        assert Decimal(lot.cost_basis_usd) == Decimal("30000.00")


class TestHoldingPeriodFunction:
    def test_exactly_365_is_short_term(self):
        acquired = datetime(2025, 1, 1)
        disposed = datetime(2026, 1, 1)
        assert _holding_period(acquired, disposed) == "short_term"

    def test_366_is_long_term(self):
        acquired = datetime(2025, 1, 1)
        disposed = datetime(2026, 1, 2)
        assert _holding_period(acquired, disposed) == "long_term"


# ---------------------------------------------------------------------------
# Fix 1: Wrapping Swap Tests
# ---------------------------------------------------------------------------


class TestWrappingSwapNoGainLoss:
    """ETH→STETH trade should create no LotAssignment (non-taxable)."""

    def test_wrapping_swap_no_gain_loss(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        eth = seed_assets["ETH"]
        steth = seed_assets["STETH"]

        # Buy 2 ETH at $3000 each
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="2.0", to_asset_id=eth.id,
            to_value_usd="6000.00",
        )
        # Wrap 1.9 ETH → 1.9 STETH (wrapping swap)
        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="trade",
            from_wallet_id=w.id, from_asset_id=eth.id, from_amount="1.9",
            to_wallet_id=w.id, to_asset_id=steth.id, to_amount="1.9",
            from_value_usd="5700.00", to_value_usd="5700.00",
        )

        # Process ETH first (source), then STETH (destination)
        result_eth = calculate_for_wallet_asset(db, w.id, eth.id, 2025)
        result_steth = calculate_for_wallet_asset(db, w.id, steth.id, 2025)

        # No gains or losses on either side
        assert result_eth["total_gains"] == "0.00"
        assert result_eth["total_losses"] == "0.00"
        assert result_steth["total_gains"] == "0.00"
        assert result_steth["total_losses"] == "0.00"

        # No LotAssignment records created
        assignments = db.query(LotAssignment).all()
        assert len(assignments) == 0


class TestWrappingSwapCarriesCostBasis:
    """STETH lot should inherit ETH cost basis and acquired_date."""

    def test_wrapping_swap_carries_cost_basis(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        eth = seed_assets["ETH"]
        steth = seed_assets["STETH"]

        buy_date = datetime(2025, 1, 1, tzinfo=timezone.utc)

        make_transaction(
            db, datetime_utc=buy_date,
            tx_type="buy", to_wallet_id=w.id,
            to_amount="2.0", to_asset_id=eth.id,
            to_value_usd="6000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="trade",
            from_wallet_id=w.id, from_asset_id=eth.id, from_amount="2.0",
            to_wallet_id=w.id, to_asset_id=steth.id, to_amount="2.0",
            from_value_usd="7000.00", to_value_usd="7000.00",
        )

        calculate_for_wallet_asset(db, w.id, eth.id, 2025)
        calculate_for_wallet_asset(db, w.id, steth.id, 2025)

        steth_lot = db.query(TaxLot).filter_by(
            wallet_id=w.id, asset_id=steth.id
        ).first()
        assert steth_lot is not None
        # Cost basis carries over from ETH ($6000), not the STETH FMV ($7000)
        assert Decimal(steth_lot.cost_basis_usd) == Decimal("6000.00")
        # Acquired date carries over from original buy (SQLite strips tzinfo)
        assert steth_lot.acquired_date == buy_date.replace(tzinfo=None)


class TestWrappingSwapThenSell:
    """Sell STETH should use original ETH cost basis for gain calculation."""

    def test_wrapping_swap_then_sell(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        eth = seed_assets["ETH"]
        steth = seed_assets["STETH"]

        # Buy 1 ETH at $3000
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=eth.id,
            to_value_usd="3000.00",
        )
        # Wrap ETH → STETH
        make_transaction(
            db, datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
            tx_type="trade",
            from_wallet_id=w.id, from_asset_id=eth.id, from_amount="1.0",
            to_wallet_id=w.id, to_asset_id=steth.id, to_amount="1.0",
            from_value_usd="3500.00", to_value_usd="3500.00",
        )
        # Sell STETH at $4000
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=steth.id,
            from_value_usd="4000.00",
        )

        calculate_for_wallet_asset(db, w.id, eth.id, 2025)
        result = calculate_for_wallet_asset(db, w.id, steth.id, 2025)

        # Gain = $4000 - $3000 (original ETH basis) = $1000
        assert result["total_gains"] == "1000.00"
        assert result["total_losses"] == "0.00"


class TestWrappingSwapPreservesHoldingPeriod:
    """Long-term if ETH held >365 days before wrapping."""

    def test_wrapping_swap_preserves_holding_period(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        eth = seed_assets["ETH"]
        steth = seed_assets["STETH"]

        # Buy ETH in 2024
        make_transaction(
            db, datetime_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=eth.id,
            to_value_usd="2000.00",
        )
        calculate_for_wallet_asset(db, w.id, eth.id, 2024)

        # Wrap in 2025
        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="trade",
            from_wallet_id=w.id, from_asset_id=eth.id, from_amount="1.0",
            to_wallet_id=w.id, to_asset_id=steth.id, to_amount="1.0",
            from_value_usd="3500.00", to_value_usd="3500.00",
        )
        # Sell STETH after >365 days from original ETH purchase
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=steth.id,
            from_value_usd="4000.00",
        )

        calculate_for_wallet_asset(db, w.id, eth.id, 2025)
        calculate_for_wallet_asset(db, w.id, steth.id, 2025)

        assignment = db.query(LotAssignment).filter_by(tax_year=2025).first()
        assert assignment is not None
        assert assignment.holding_period == "long_term"


class TestUnwrappingSwap:
    """STETH→ETH should also be non-taxable."""

    def test_unwrapping_swap(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        eth = seed_assets["ETH"]
        steth = seed_assets["STETH"]

        # Buy STETH
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=steth.id,
            to_value_usd="3000.00",
        )
        # Unwrap STETH → ETH
        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="trade",
            from_wallet_id=w.id, from_asset_id=steth.id, from_amount="1.0",
            to_wallet_id=w.id, to_asset_id=eth.id, to_amount="1.0",
            from_value_usd="3500.00", to_value_usd="3500.00",
        )

        result_steth = calculate_for_wallet_asset(db, w.id, steth.id, 2025)
        result_eth = calculate_for_wallet_asset(db, w.id, eth.id, 2025)

        # No gains or losses
        assert result_steth["total_gains"] == "0.00"
        assert result_steth["total_losses"] == "0.00"
        assert result_eth["total_gains"] == "0.00"
        assert result_eth["total_losses"] == "0.00"

        # ETH lot has STETH's original cost basis
        eth_lot = db.query(TaxLot).filter_by(
            wallet_id=w.id, asset_id=eth.id
        ).first()
        assert Decimal(eth_lot.cost_basis_usd) == Decimal("3000.00")


class TestNormalTradeNotAffected:
    """ETH→BTC should still be taxable (not a wrapping pair)."""

    def test_normal_trade_not_affected(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        eth = seed_assets["ETH"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=eth.id,
            to_value_usd="3000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="trade",
            from_wallet_id=w.id, from_asset_id=eth.id, from_amount="1.0",
            to_wallet_id=w.id, to_asset_id=btc.id, to_amount="0.05",
            from_value_usd="3500.00", to_value_usd="3500.00",
        )

        result = calculate_for_wallet_asset(db, w.id, eth.id, 2025)

        # Normal trade creates a taxable disposal: $3500 - $3000 = $500 gain
        assert result["total_gains"] == "500.00"

        # LotAssignment should exist
        assignments = db.query(LotAssignment).all()
        assert len(assignments) == 1


# ---------------------------------------------------------------------------
# Fix 2: Unmatched Withdrawal Tests
# ---------------------------------------------------------------------------


class TestUnmatchedWithdrawalCreatesDisposal:
    """Unmatched BTC withdrawal should create a LotAssignment."""

    def test_unmatched_withdrawal_creates_disposal(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="withdrawal",
            from_wallet_id=w.id, from_asset_id=btc.id, from_amount="0.5",
            from_value_usd="20000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        assignments = db.query(LotAssignment).all()
        assert len(assignments) == 1
        assert Decimal(assignments[0].proceeds_usd) == Decimal("20000.00")


class TestUnmatchedWithdrawalGain:
    """Unmatched withdrawal gain = proceeds - cost basis."""

    def test_unmatched_withdrawal_gain(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="20000.00",
        )
        # Withdrawal at higher FMV
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="withdrawal",
            from_wallet_id=w.id, from_asset_id=btc.id, from_amount="1.0",
            from_value_usd="35000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        # Gain = $35k - $20k = $15k
        assert result["total_gains"] == "15000.00"
        assert result["total_losses"] == "0.00"


class TestUnmatchedWithdrawalLoss:
    """Loss when FMV at withdrawal < cost basis."""

    def test_unmatched_withdrawal_loss(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="50000.00",
        )
        # Withdrawal at lower FMV
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="withdrawal",
            from_wallet_id=w.id, from_asset_id=btc.id, from_amount="1.0",
            from_value_usd="30000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        assert result["total_gains"] == "0.00"
        assert result["total_losses"] == "20000.00"
        assert result["net_gain_loss"] == "-20000.00"


class TestWithdrawalWithDepositStillTaxable:
    """All withdrawals are taxable disposals, even when paired with a deposit."""

    def test_withdrawal_with_deposit_still_taxable(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        atom = seed_assets["ATOM"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="100.0", to_asset_id=atom.id,
            to_value_usd="1000.00",
        )
        # Staking claim fee pattern: tiny withdrawal + large deposit at same time
        ts = datetime(2025, 3, 1, tzinfo=timezone.utc)
        make_transaction(
            db, datetime_utc=ts,
            tx_type="withdrawal",
            from_wallet_id=w.id, from_asset_id=atom.id, from_amount="0.1",
            from_value_usd="1.00",
        )
        make_transaction(
            db, datetime_utc=ts,
            tx_type="deposit",
            to_wallet_id=w.id, to_asset_id=atom.id, to_amount="5.0",
            to_value_usd="50.00",
        )

        result = calculate_for_wallet_asset(db, w.id, atom.id, 2025)

        # Withdrawal IS a taxable disposal (Koinly treats staking fees as disposals)
        assignments = db.query(LotAssignment).all()
        assert len(assignments) == 1
        assert Decimal(assignments[0].proceeds_usd) == Decimal("1.00")


class TestUnmatchedWithdrawalInsufficientLots:
    """Unmatched withdrawal with no lots should set tax error."""

    def test_unmatched_withdrawal_insufficient_lots(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # No buy — straight to withdrawal
        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="withdrawal",
            from_wallet_id=w.id, from_asset_id=btc.id, from_amount="1.0",
            from_value_usd="30000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        assert result["error_count"] == 1
