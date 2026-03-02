"""Tests for tax error surfacing & correction."""

import pytest
from datetime import datetime, timezone

from app.models import Transaction
from app.services.tax_engine import (
    calculate_for_wallet_asset,
    recalculate_all,
)
from app.tests.conftest import make_transaction


class TestTaxErrorMarking:
    """Sell without a prior buy should mark has_tax_error=True."""

    def test_sell_without_buy_marks_error(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        usd = seed_assets["USD"]

        # Create a sell with no prior buy
        sell_tx = make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="40000.00", to_asset_id=usd.id,
            from_value_usd="40000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        db.refresh(sell_tx)
        assert sell_tx.has_tax_error is True
        assert sell_tx.tax_error is not None
        assert "Insufficient lots" in sell_tx.tax_error
        assert result["error_count"] == 1

    def test_trade_disposal_without_lots_marks_error(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        eth = seed_assets["ETH"]

        # Trade BTC->ETH with no prior BTC lots
        trade_tx = make_transaction(
            db, datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="trade", from_wallet_id=w.id, to_wallet_id=w.id,
            from_amount="0.5", from_asset_id=btc.id,
            to_amount="8.0", to_asset_id=eth.id,
            from_value_usd="20000.00", to_value_usd="20000.00",
        )

        result = calculate_for_wallet_asset(db, w.id, btc.id, 2025)

        db.refresh(trade_tx)
        assert trade_tx.has_tax_error is True
        assert "Insufficient lots" in trade_tx.tax_error


class TestTaxErrorClearing:
    """Adding a buy then recalculating should clear errors."""

    def test_add_buy_then_recalculate_clears_error(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        usd = seed_assets["USD"]

        # Create sell without buy
        sell_tx = make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="40000.00", to_asset_id=usd.id,
            from_value_usd="40000.00",
        )

        calculate_for_wallet_asset(db, w.id, btc.id, 2025)
        db.refresh(sell_tx)
        assert sell_tx.has_tax_error is True

        # Now add a buy before the sell
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            from_amount="30000.00", from_asset_id=usd.id,
            to_value_usd="30000.00",
        )

        # Recalculate should clear the error
        from app.services.tax_engine import recalculate_for_wallet_asset
        result = recalculate_for_wallet_asset(db, w.id, btc.id, 2025)

        db.refresh(sell_tx)
        assert sell_tx.has_tax_error is False
        assert sell_tx.tax_error is None
        assert result["total_gains"] == "10000.00"


class TestRecalculateAllErrors:
    """recalculate_all returns error_transaction_count."""

    def test_recalculate_all_returns_error_count(self, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        usd = seed_assets["USD"]

        # Sell without buy
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="40000.00", to_asset_id=usd.id,
            from_value_usd="40000.00",
        )

        data = recalculate_all(db, tax_year=2025)
        assert data["error_transaction_count"] >= 1


class TestHasErrorsFilter:
    """has_errors filter on list endpoint."""

    def test_filter_transactions_by_error(self, client, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        usd = seed_assets["USD"]

        # Create a valid buy
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy", to_wallet_id=w.id,
            to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )

        # Create a sell without buy (insufficient lots for 2.0 when only 1.0 available)
        sell_tx = make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="2.0", from_asset_id=btc.id,
            to_amount="80000.00", to_asset_id=usd.id,
            from_value_usd="80000.00",
        )

        # Run calculation to mark errors
        calculate_for_wallet_asset(db, w.id, btc.id, 2025)
        db.commit()

        # Filter for errors
        resp = client.get("/api/transactions?has_errors=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert all(item["has_tax_error"] for item in data["items"])

        # Filter for non-errors
        resp2 = client.get("/api/transactions?has_errors=false")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert all(not item["has_tax_error"] for item in data2["items"])

    def test_error_count_endpoint(self, client, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        usd = seed_assets["USD"]

        # Sell without buy
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="40000.00", to_asset_id=usd.id,
            from_value_usd="40000.00",
        )

        calculate_for_wallet_asset(db, w.id, btc.id, 2025)
        db.commit()

        resp = client.get("/api/transactions/error-count")
        assert resp.status_code == 200
        assert resp.json()["error_count"] >= 1


class TestEditClearsErrors:
    """Editing a transaction clears error flags."""

    def test_update_clears_tax_error(self, client, db, seed_wallets, seed_assets, seed_settings):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        usd = seed_assets["USD"]

        # Create a sell with no buy
        sell_tx = make_transaction(
            db, datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell", from_wallet_id=w.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="40000.00", to_asset_id=usd.id,
            from_value_usd="40000.00",
        )

        # Mark error via engine
        calculate_for_wallet_asset(db, w.id, btc.id, 2025)
        db.commit()
        db.refresh(sell_tx)
        assert sell_tx.has_tax_error is True

        # Edit the transaction
        resp = client.put(
            f"/api/transactions/{sell_tx.id}",
            json={"label": "corrected"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_tax_error"] is False
        assert data["tax_error"] is None

        # Verify in DB
        db.refresh(sell_tx)
        assert sell_tx.has_tax_error is False
        assert sell_tx.tax_error is None
