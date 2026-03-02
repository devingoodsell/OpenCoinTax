"""Tests for invariant checks."""

from datetime import datetime, timezone
from decimal import Decimal

from app.models import TaxLot, LotAssignment
from app.services.invariant_checker import (
    check_balance, check_gain_loss_math, check_negative_remaining,
    check_temporal_consistency, check_double_spend, run_all_checks,
)
from app.services.tax_engine import calculate_for_wallet_asset
from app.tests.conftest import make_transaction


class TestAllChecksPassOnValidData:
    def test_clean_data(self, db, seed_wallets, seed_assets, seed_settings):
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
            from_amount="0.5", from_asset_id=btc.id,
            from_value_usd="20000.00",
        )

        calculate_for_wallet_asset(db, w.id, btc.id, 2025)
        db.commit()

        results = run_all_checks(db)
        for r in results:
            assert r.status == "pass", f"Check {r.check_name} failed: {r.details}"


class TestGainLossMathFails:
    def test_bad_math_detected(self, db, seed_wallets, seed_assets, seed_settings):
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

        calculate_for_wallet_asset(db, w.id, btc.id, 2025)
        db.commit()

        # Tamper with a lot assignment to introduce bad math
        assignment = db.query(LotAssignment).first()
        assignment.gain_loss_usd = "99999.00"  # Wrong!
        db.commit()

        results = check_gain_loss_math(db)
        failed = [r for r in results if r.status == "fail"]
        assert len(failed) == 1


class TestNegativeRemainingDetected:
    def test_negative_caught(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        tx = make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )

        # Manually create a lot with negative remaining
        lot = TaxLot(
            wallet_id=w.id, asset_id=btc.id,
            amount="1.0", remaining_amount="-0.5",
            cost_basis_usd="30000.00", cost_basis_per_unit="30000.00",
            acquired_date=tx.datetime_utc, acquisition_tx_id=tx.id,
            source_type="purchase",
        )
        db.add(lot)
        db.commit()

        results = check_negative_remaining(db)
        failed = [r for r in results if r.status == "fail"]
        assert len(failed) == 1


class TestDoubleSpendDetected:
    def test_over_assignment_caught(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        buy_tx = make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )

        lot = TaxLot(
            wallet_id=w.id, asset_id=btc.id,
            amount="1.0", remaining_amount="0.0",
            cost_basis_usd="30000.00", cost_basis_per_unit="30000.00",
            acquired_date=buy_tx.datetime_utc, acquisition_tx_id=buy_tx.id,
            source_type="purchase", is_fully_disposed=True,
        )
        db.add(lot)
        db.commit()
        db.refresh(lot)

        sell_tx = make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            from_value_usd="40000.00",
        )

        # Over-assign: create two assignments totaling more than lot amount
        a1 = LotAssignment(
            disposal_tx_id=sell_tx.id, tax_lot_id=lot.id,
            amount="0.8", cost_basis_usd="24000.00", proceeds_usd="32000.00",
            gain_loss_usd="8000.00", holding_period="short_term",
            cost_basis_method="fifo", tax_year=2025,
        )
        a2 = LotAssignment(
            disposal_tx_id=sell_tx.id, tax_lot_id=lot.id,
            amount="0.5", cost_basis_usd="15000.00", proceeds_usd="20000.00",
            gain_loss_usd="5000.00", holding_period="short_term",
            cost_basis_method="fifo", tax_year=2025,
        )
        db.add_all([a1, a2])
        db.commit()

        results = check_double_spend(db)
        failed = [r for r in results if r.status == "fail"]
        assert len(failed) == 1
