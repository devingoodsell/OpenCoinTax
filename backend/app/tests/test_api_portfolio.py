"""Integration tests for portfolio API routes."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import PriceHistory, TaxLot, LotAssignment
from app.tests.conftest import make_transaction


@pytest.fixture
def portfolio_seed(db, seed_assets, seed_wallets, seed_settings):
    """Seed transactions, tax lots, lot assignments, and price history
    that mirror the scenario from the standalone portfolio tests."""
    btc = seed_assets["BTC"]
    eth = seed_assets["ETH"]
    wallet = seed_wallets["Coinbase"]

    # Transactions
    tx1 = make_transaction(
        db,
        datetime_utc=datetime(2025, 1, 15, tzinfo=timezone.utc),
        tx_type="buy",
        to_wallet_id=wallet.id,
        to_asset_id=btc.id,
        to_amount="1.0",
        to_value_usd="40000.00",
        fee_value_usd="10.00",
    )
    tx2 = make_transaction(
        db,
        datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
        tx_type="buy",
        to_wallet_id=wallet.id,
        to_asset_id=eth.id,
        to_amount="10.0",
        to_value_usd="20000.00",
        fee_value_usd="5.00",
    )
    tx3 = make_transaction(
        db,
        datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
        tx_type="sell",
        from_wallet_id=wallet.id,
        from_asset_id=btc.id,
        from_amount="0.5",
        from_value_usd="25000.00",
        fee_value_usd="8.00",
    )
    tx4 = make_transaction(
        db,
        datetime_utc=datetime(2025, 2, 15, tzinfo=timezone.utc),
        tx_type="staking_reward",
        to_wallet_id=wallet.id,
        to_asset_id=eth.id,
        to_amount="0.5",
        to_value_usd="1000.00",
        fee_value_usd="0.00",
    )

    # Tax lots
    lot1 = TaxLot(
        wallet_id=wallet.id,
        asset_id=btc.id,
        amount="1.0",
        remaining_amount="0.5",
        cost_basis_usd="40000.00",
        cost_basis_per_unit="40000.00",
        acquired_date=datetime(2025, 1, 15),
        acquisition_tx_id=tx1.id,
        source_type="purchase",
        is_fully_disposed=False,
    )
    lot2 = TaxLot(
        wallet_id=wallet.id,
        asset_id=eth.id,
        amount="10.0",
        remaining_amount="10.0",
        cost_basis_usd="20000.00",
        cost_basis_per_unit="2000.00",
        acquired_date=datetime(2025, 2, 1),
        acquisition_tx_id=tx2.id,
        source_type="purchase",
        is_fully_disposed=False,
    )
    lot3 = TaxLot(
        wallet_id=wallet.id,
        asset_id=eth.id,
        amount="0.5",
        remaining_amount="0.5",
        cost_basis_usd="1000.00",
        cost_basis_per_unit="2000.00",
        acquired_date=datetime(2025, 2, 15),
        acquisition_tx_id=tx4.id,
        source_type="income",
        is_fully_disposed=False,
    )
    db.add_all([lot1, lot2, lot3])
    db.flush()

    # Lot assignment for the sell
    la = LotAssignment(
        disposal_tx_id=tx3.id,
        tax_lot_id=lot1.id,
        amount="0.5",
        cost_basis_usd="20000.00",
        proceeds_usd="25000.00",
        gain_loss_usd="5000.00",
        holding_period="short_term",
        cost_basis_method="fifo",
        tax_year=2025,
    )
    db.add(la)
    db.flush()

    # Price history — BTC: Jan 15 – Mar 31, ETH: Feb 1 – Mar 31
    prices = []
    btc_base = 40000
    d = date(2025, 1, 15)
    while d <= date(2025, 3, 31):
        prices.append(PriceHistory(
            asset_id=btc.id,
            date=d,
            price_usd=str(btc_base + (d - date(2025, 1, 15)).days * 100),
            source="test",
        ))
        d += timedelta(days=1)

    eth_base = 2000
    d = date(2025, 2, 1)
    while d <= date(2025, 3, 31):
        prices.append(PriceHistory(
            asset_id=eth.id,
            date=d,
            price_usd=str(eth_base + (d - date(2025, 2, 1)).days * 20),
            source="test",
        ))
        d += timedelta(days=1)

    db.add_all(prices)
    db.commit()

    return {
        "btc": btc,
        "eth": eth,
        "wallet": wallet,
        "lots": [lot1, lot2, lot3],
        "transactions": [tx1, tx2, tx3, tx4],
    }


class TestDailyValues:
    def test_returns_data_for_date_range(self, client, portfolio_seed):
        resp = client.get(
            "/api/portfolio/daily-values",
            params={"start_date": "2025-02-01", "end_date": "2025-02-05"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data_points"]) == 5
        assert body["data_points"][0]["date"] == "2025-02-01"
        assert body["data_points"][4]["date"] == "2025-02-05"
        for dp in body["data_points"]:
            assert Decimal(dp["total_value_usd"]) > 0

    def test_summary_has_unrealized_gain(self, client, portfolio_seed):
        resp = client.get(
            "/api/portfolio/daily-values",
            params={"start_date": "2025-03-01", "end_date": "2025-03-01"},
        )
        assert resp.status_code == 200
        summary = resp.json()["summary"]
        assert "current_value" in summary
        assert "unrealized_gain" in summary
        assert "unrealized_gain_pct" in summary

    def test_empty_range_returns_zero_values(self, client, portfolio_seed):
        resp = client.get(
            "/api/portfolio/daily-values",
            params={"start_date": "2020-01-01", "end_date": "2020-01-05"},
        )
        assert resp.status_code == 200
        body = resp.json()
        for dp in body["data_points"]:
            assert dp["total_value_usd"] == "0.00"

    def test_no_lots_at_all(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get(
            "/api/portfolio/daily-values",
            params={"start_date": "2025-01-01", "end_date": "2025-01-05"},
        )
        assert resp.status_code == 200
        assert resp.json()["data_points"] == []


class TestHoldings:
    def test_aggregates_across_lots(self, client, portfolio_seed):
        resp = client.get("/api/portfolio/holdings")
        assert resp.status_code == 200
        holdings = resp.json()["holdings"]
        symbols = {h["asset_symbol"] for h in holdings}
        assert "BTC" in symbols
        assert "ETH" in symbols

    def test_btc_quantity_reflects_partial_disposal(self, client, portfolio_seed):
        resp = client.get("/api/portfolio/holdings")
        btc = next(h for h in resp.json()["holdings"] if h["asset_symbol"] == "BTC")
        assert Decimal(btc["total_quantity"]) == Decimal("0.5")

    def test_eth_quantity_includes_staking_lot(self, client, portfolio_seed):
        resp = client.get("/api/portfolio/holdings")
        eth = next(h for h in resp.json()["holdings"] if h["asset_symbol"] == "ETH")
        # lot2 = 10 + lot3 = 0.5 = 10.5
        assert Decimal(eth["total_quantity"]) == Decimal("10.5")

    def test_allocation_sums_to_100(self, client, portfolio_seed):
        resp = client.get("/api/portfolio/holdings")
        holdings = resp.json()["holdings"]
        total_alloc = sum(
            Decimal(h["allocation_pct"])
            for h in holdings
            if h["allocation_pct"] is not None
        )
        assert abs(total_alloc - Decimal("100")) < Decimal("1")

    def test_empty_portfolio(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/portfolio/holdings")
        assert resp.status_code == 200
        assert resp.json()["holdings"] == []
        assert resp.json()["total_portfolio_value"] == "0.00"

    def test_holdings_without_tax_lots(self, client, db, seed_assets, seed_wallets, seed_settings):
        """Holdings should appear from transactions alone — no tax lots required."""
        btc = seed_assets["BTC"]
        wallet = seed_wallets["Coinbase"]

        # Create buy and sell transactions but NO tax lots
        make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 10, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=btc.id,
            to_amount="2.0",
            to_value_usd="80000.00",
        )
        make_transaction(
            db,
            datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
            tx_type="sell",
            from_wallet_id=wallet.id,
            from_asset_id=btc.id,
            from_amount="0.5",
            from_value_usd="25000.00",
        )

        # Add a price so market value can be computed
        db.add(PriceHistory(
            asset_id=btc.id, date=date(2025, 3, 1),
            price_usd="50000.00", source="test",
        ))
        db.commit()

        resp = client.get("/api/portfolio/holdings")
        assert resp.status_code == 200
        holdings = resp.json()["holdings"]
        assert len(holdings) == 1
        btc_holding = holdings[0]
        assert btc_holding["asset_symbol"] == "BTC"
        # 2.0 bought - 0.5 sold = 1.5
        assert Decimal(btc_holding["total_quantity"]) == Decimal("1.50000000")
        # Cost basis should be 0 (no tax lots)
        assert Decimal(btc_holding["total_cost_basis_usd"]) == Decimal("0.00")
        # Market value = 1.5 * 50000 = 75000
        assert Decimal(btc_holding["market_value_usd"]) == Decimal("75000.00")


class TestPortfolioStats:
    def test_aggregates_transactions(self, client, portfolio_seed):
        resp = client.get(
            "/api/portfolio/stats",
            params={"start_date": "2025-01-01", "end_date": "2025-12-31"},
        )
        assert resp.status_code == 200
        body = resp.json()

        # Buy tx1 = 40000, buy tx2 = 20000 -> total_in = 60000
        assert Decimal(body["total_in"]) == Decimal("60000.00")
        # Sell tx3 = 25000 -> total_out = 25000
        assert Decimal(body["total_out"]) == Decimal("25000.00")
        # Staking reward tx4 = 1000 -> total_income = 1000
        assert Decimal(body["total_income"]) == Decimal("1000.00")
        # Fees: 10 + 5 + 8 + 0 = 23
        assert Decimal(body["total_fees"]) == Decimal("23.00")
        # Realized gains from lot assignment: 5000
        assert Decimal(body["realized_gains"]) == Decimal("5000.00")

    def test_narrow_date_range(self, client, portfolio_seed):
        resp = client.get(
            "/api/portfolio/stats",
            params={"start_date": "2025-02-01", "end_date": "2025-02-28"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Only tx2 (buy 20000) and tx4 (staking 1000) in Feb
        assert Decimal(body["total_in"]) == Decimal("20000.00")
        assert Decimal(body["total_income"]) == Decimal("1000.00")
        # No sells in Feb
        assert Decimal(body["total_out"]) == Decimal("0.00")

    def test_empty_range(self, client, portfolio_seed):
        resp = client.get(
            "/api/portfolio/stats",
            params={"start_date": "2020-01-01", "end_date": "2020-12-31"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert Decimal(body["total_in"]) == Decimal("0.00")
        assert Decimal(body["realized_gains"]) == Decimal("0.00")
