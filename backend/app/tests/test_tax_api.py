"""Integration tests for the wired-up tax API endpoints.

Tests POST /api/tax/recalculate, GET /api/tax/summary/{year},
GET /api/tax/gains/{year}, GET /api/tax/lots, POST /api/tax/validate,
and GET /api/tax/compare-methods/{year}.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.models import (
    Asset, TaxLot, LotAssignment, Transaction, Setting,
    TransactionType, HoldingPeriod, CostBasisMethod,
)
from app.services.tax_engine import calculate_for_wallet_asset
from app.tests.conftest import make_transaction


TAX_YEAR = 2025
BUY_DATE = datetime(2025, 1, 15)
SELL_DATE = datetime(2025, 6, 15)


def _get_usd(db):
    return db.query(Asset).filter(Asset.symbol == "USD").first()


def _buy_and_sell(db, wallet, btc, *, buy_usd="30000.00", sell_usd="35000.00",
                  buy_amount="1.0", sell_amount="1.0",
                  buy_date=None, sell_date=None):
    """Create a buy and sell transaction pair and return them."""
    usd = _get_usd(db)
    buy_date = buy_date or BUY_DATE
    sell_date = sell_date or SELL_DATE

    buy_tx = make_transaction(
        db, datetime_utc=buy_date,
        tx_type=TransactionType.buy.value,
        to_wallet_id=wallet.id, to_amount=buy_amount, to_asset_id=btc.id,
        from_amount=buy_usd, from_asset_id=usd.id,
        to_value_usd=buy_usd, from_value_usd=buy_usd, net_value_usd=buy_usd,
    )
    sell_tx = make_transaction(
        db, datetime_utc=sell_date,
        tx_type=TransactionType.sell.value,
        from_wallet_id=wallet.id, from_amount=sell_amount, from_asset_id=btc.id,
        to_amount=sell_usd, to_asset_id=usd.id,
        from_value_usd=sell_usd, to_value_usd=sell_usd, net_value_usd=sell_usd,
    )
    return buy_tx, sell_tx


class TestRecalculateEndpoint:

    def test_recalculate_creates_lots_and_assignments(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """POST /api/tax/recalculate processes transactions and creates lots/assignments."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        _buy_and_sell(db, wallet, btc)

        resp = client.post(f"/api/tax/recalculate?year={TAX_YEAR}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pairs_processed"] >= 1

        # Verify lot assignment was created
        assignments = db.query(LotAssignment).filter(
            LotAssignment.tax_year == TAX_YEAR
        ).all()
        assert len(assignments) >= 1

    def test_recalculate_empty(self, client, db, seed_assets, seed_wallets, seed_settings):
        """Recalculate with no transactions succeeds with 0 pairs."""
        resp = client.post(f"/api/tax/recalculate?year={TAX_YEAR}")
        assert resp.status_code == 200
        assert resp.json()["pairs_processed"] == 0


class TestTaxSummaryEndpoint:

    def test_summary_with_gains(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """GET /api/tax/summary/{year} returns aggregate summary."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        _buy_and_sell(db, wallet, btc, buy_usd="30000.00", sell_usd="35000.00")
        calculate_for_wallet_asset(db, wallet.id, btc.id, TAX_YEAR)

        resp = client.get(f"/api/tax/summary/{TAX_YEAR}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tax_year"] == TAX_YEAR
        assert Decimal(data["total_proceeds"]) == Decimal("35000.00")
        assert Decimal(data["total_cost_basis"]) == Decimal("30000.00")
        assert Decimal(data["short_term_gains"]) == Decimal("5000.00")
        assert Decimal(data["net_gain_loss"]) == Decimal("5000.00")

    def test_summary_empty_year(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """Empty year returns all zeros."""
        resp = client.get(f"/api/tax/summary/{TAX_YEAR}")
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(data["total_proceeds"]) == Decimal("0.00")
        assert Decimal(data["total_income"]) == Decimal("0.00")

    def test_summary_includes_income(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """Summary includes income from staking rewards."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1),
            tx_type=TransactionType.staking_reward.value,
            to_wallet_id=wallet.id, to_amount="0.01", to_asset_id=btc.id,
            to_value_usd="500.00",
        )

        resp = client.get(f"/api/tax/summary/{TAX_YEAR}")
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(data["staking_income"]) == Decimal("500.00")
        assert Decimal(data["total_income"]) == Decimal("500.00")


class TestGainsEndpoint:

    def test_gains_list(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """GET /api/tax/gains/{year} returns realized gains/losses."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        _buy_and_sell(db, wallet, btc)
        calculate_for_wallet_asset(db, wallet.id, btc.id, TAX_YEAR)

        resp = client.get(f"/api/tax/gains/{TAX_YEAR}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["asset_symbol"] == "BTC"
        assert Decimal(item["gain_loss_usd"]) == Decimal("5000.00")
        assert item["holding_period"] == "short_term"

    def test_gains_empty(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """No assignments → empty gains list."""
        resp = client.get(f"/api/tax/gains/{TAX_YEAR}")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestLotsEndpoint:

    def test_lots_list(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """GET /api/tax/lots returns tax lots."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        usd = _get_usd(db)

        # Just buy — creates a lot
        make_transaction(
            db, datetime_utc=BUY_DATE,
            tx_type=TransactionType.buy.value,
            to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
            from_amount="30000.00", from_asset_id=usd.id,
            to_value_usd="30000.00", from_value_usd="30000.00",
            net_value_usd="30000.00",
        )
        calculate_for_wallet_asset(db, wallet.id, btc.id, TAX_YEAR)

        resp = client.get("/api/tax/lots")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

        lot = data["items"][0]
        assert lot["asset_symbol"] == "BTC"
        assert Decimal(lot["amount"]) == Decimal("1.0")

    def test_lots_filter_by_asset(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """GET /api/tax/lots?asset_id=X filters by asset."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        eth = seed_assets["ETH"]
        usd = _get_usd(db)

        make_transaction(
            db, datetime_utc=BUY_DATE,
            tx_type=TransactionType.buy.value,
            to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
            from_amount="30000.00", from_asset_id=usd.id,
            to_value_usd="30000.00", from_value_usd="30000.00",
        )
        make_transaction(
            db, datetime_utc=BUY_DATE,
            tx_type=TransactionType.buy.value,
            to_wallet_id=wallet.id, to_amount="10.0", to_asset_id=eth.id,
            from_amount="20000.00", from_asset_id=usd.id,
            to_value_usd="20000.00", from_value_usd="20000.00",
        )
        calculate_for_wallet_asset(db, wallet.id, btc.id, TAX_YEAR)
        calculate_for_wallet_asset(db, wallet.id, eth.id, TAX_YEAR)

        # Filter to BTC only
        resp = client.get(f"/api/tax/lots?asset_id={btc.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert all(item["asset_id"] == btc.id for item in data["items"])


class TestValidateEndpoint:

    def test_validate_passes(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """POST /api/tax/validate on clean data passes all checks."""
        resp = client.post("/api/tax/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["all_passed"] is True
        assert len(data["results"]) > 0

    def test_validate_after_engine(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """Validation passes after running tax engine."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        _buy_and_sell(db, wallet, btc)
        calculate_for_wallet_asset(db, wallet.id, btc.id, TAX_YEAR)

        resp = client.post("/api/tax/validate")
        assert resp.status_code == 200
        assert resp.json()["all_passed"] is True


class TestCompareMethodsEndpoint:

    def test_compare_methods(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """GET /api/tax/compare-methods/{year} compares FIFO, LIFO, HIFO."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        usd = _get_usd(db)

        # Two buys at different prices, then sell partial
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1),
            tx_type=TransactionType.buy.value,
            to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
            from_amount="25000.00", from_asset_id=usd.id,
            to_value_usd="25000.00", from_value_usd="25000.00",
            net_value_usd="25000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 2, 1),
            tx_type=TransactionType.buy.value,
            to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
            from_amount="35000.00", from_asset_id=usd.id,
            to_value_usd="35000.00", from_value_usd="35000.00",
            net_value_usd="35000.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1),
            tx_type=TransactionType.sell.value,
            from_wallet_id=wallet.id, from_amount="1.0", from_asset_id=btc.id,
            to_amount="30000.00", to_asset_id=usd.id,
            from_value_usd="30000.00", to_value_usd="30000.00",
            net_value_usd="30000.00",
        )

        resp = client.get(f"/api/tax/compare-methods/{TAX_YEAR}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tax_year"] == TAX_YEAR
        assert len(data["comparisons"]) == 3

        methods = {c["method"] for c in data["comparisons"]}
        assert methods == {"fifo", "lifo", "hifo"}

        # FIFO sells the $25k lot → $5k gain
        fifo = next(c for c in data["comparisons"] if c["method"] == "fifo")
        assert Decimal(fifo["net_gain_loss"]) == Decimal("5000.00")

        # HIFO sells the $35k lot → -$5k loss
        hifo = next(c for c in data["comparisons"] if c["method"] == "hifo")
        assert Decimal(hifo["net_gain_loss"]) == Decimal("-5000.00")

        # LIFO sells the $35k lot (newest) → -$5k loss
        lifo = next(c for c in data["comparisons"] if c["method"] == "lifo")
        assert Decimal(lifo["net_gain_loss"]) == Decimal("-5000.00")
