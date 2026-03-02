"""Tests for Epic 11 advanced features — what-if analysis, specific ID, edge cases."""

from datetime import datetime
from decimal import Decimal

import pytest

from app.models import (
    Asset, TaxLot, LotAssignment, Transaction,
    TransactionType, HoldingPeriod,
)
from app.services.whatif import whatif_analysis
from app.services.tax_engine import calculate_for_wallet_asset
from app.tests.conftest import make_transaction

TAX_YEAR = 2025


def _get_usd(db):
    return db.query(Asset).filter(Asset.symbol == "USD").first()


def _setup_two_buys_and_sell(db, wallet, btc, *, run_engine=True):
    """Create 2 buys at different prices, then 1 sell. Return the sell tx.

    If run_engine=True, runs the engine (processes buys+sell, consuming lots).
    If run_engine=False, only creates lots from buys — sell is left unprocessed
    so what-if analysis can simulate all methods against both open lots.
    """
    usd = _get_usd(db)
    # Buy 1: 1 BTC at $25,000
    buy1 = make_transaction(
        db, datetime_utc=datetime(2025, 1, 1),
        tx_type=TransactionType.buy.value,
        to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
        from_amount="25000.00", from_asset_id=usd.id,
        to_value_usd="25000.00", from_value_usd="25000.00",
        net_value_usd="25000.00",
    )
    # Buy 2: 1 BTC at $35,000
    buy2 = make_transaction(
        db, datetime_utc=datetime(2025, 2, 1),
        tx_type=TransactionType.buy.value,
        to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
        from_amount="35000.00", from_asset_id=usd.id,
        to_value_usd="35000.00", from_value_usd="35000.00",
        net_value_usd="35000.00",
    )

    if not run_engine:
        # Manually create lots from buys so what-if has open lots to analyze
        from app.services.tax_engine import _create_lot, _source_type_for_tx
        _create_lot(
            db, wallet_id=wallet.id, asset_id=btc.id,
            amount=Decimal("1.0"), cost_basis_usd=Decimal("25000.00"),
            acquired_date=buy1.datetime_utc, acquisition_tx_id=buy1.id,
            source_type=_source_type_for_tx(TransactionType.buy.value),
        )
        _create_lot(
            db, wallet_id=wallet.id, asset_id=btc.id,
            amount=Decimal("1.0"), cost_basis_usd=Decimal("35000.00"),
            acquired_date=buy2.datetime_utc, acquisition_tx_id=buy2.id,
            source_type=_source_type_for_tx(TransactionType.buy.value),
        )
        db.flush()

    # Sell 1 BTC at $30,000
    sell_tx = make_transaction(
        db, datetime_utc=datetime(2025, 6, 1),
        tx_type=TransactionType.sell.value,
        from_wallet_id=wallet.id, from_amount="1.0", from_asset_id=btc.id,
        to_amount="30000.00", to_asset_id=usd.id,
        from_value_usd="30000.00", to_value_usd="30000.00",
        net_value_usd="30000.00",
    )

    if run_engine:
        calculate_for_wallet_asset(db, wallet.id, btc.id, TAX_YEAR)

    return sell_tx


class TestWhatIfAnalysis:

    def test_whatif_returns_three_methods(self, db, seed_assets, seed_wallets, seed_settings):
        """What-if analysis returns FIFO, LIFO, HIFO comparisons."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        sell_tx = _setup_two_buys_and_sell(db, wallet, btc, run_engine=False)

        result = whatif_analysis(db, sell_tx.id)

        assert result["transaction_id"] == sell_tx.id
        assert "fifo" in result["methods"]
        assert "lifo" in result["methods"]
        assert "hifo" in result["methods"]
        assert result["most_tax_efficient"] is not None

    def test_whatif_fifo_vs_hifo(self, db, seed_assets, seed_wallets, seed_settings):
        """FIFO uses cheaper lot ($25k) → $5k gain; HIFO uses $35k lot → -$5k loss."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        sell_tx = _setup_two_buys_and_sell(db, wallet, btc, run_engine=False)

        result = whatif_analysis(db, sell_tx.id)

        # FIFO: sells $25k lot → gain $5k
        fifo = result["methods"]["fifo"]
        assert fifo["error"] is None
        assert Decimal(fifo["total_gain_loss"]) == Decimal("5000.00")

        # HIFO: sells $35k lot → loss $5k
        hifo = result["methods"]["hifo"]
        assert hifo["error"] is None
        assert Decimal(hifo["total_gain_loss"]) == Decimal("-5000.00")

        # Most tax efficient should be HIFO or LIFO (both select the $35k lot)
        assert result["most_tax_efficient"] in ("hifo", "lifo")

    def test_whatif_shows_lots_used(self, db, seed_assets, seed_wallets, seed_settings):
        """Each method shows which lots would be used."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        sell_tx = _setup_two_buys_and_sell(db, wallet, btc, run_engine=False)

        result = whatif_analysis(db, sell_tx.id)
        fifo = result["methods"]["fifo"]
        assert len(fifo["lots_used"]) >= 1
        assert "lot_id" in fifo["lots_used"][0]
        assert "cost_basis_usd" in fifo["lots_used"][0]

    def test_whatif_invalid_transaction(self, db, seed_assets, seed_wallets, seed_settings):
        """What-if on a non-existent transaction raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            whatif_analysis(db, 99999)

    def test_whatif_non_disposal(self, db, seed_assets, seed_wallets, seed_settings):
        """What-if on a buy transaction raises ValueError."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        usd = _get_usd(db)
        buy_tx = make_transaction(
            db, datetime_utc=datetime(2025, 1, 1),
            tx_type=TransactionType.buy.value,
            to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
            from_amount="30000.00", from_asset_id=usd.id,
            to_value_usd="30000.00", from_value_usd="30000.00",
        )
        with pytest.raises(ValueError, match="not a disposal"):
            whatif_analysis(db, buy_tx.id)


class TestWhatIfAPI:

    def test_whatif_endpoint(self, client, db, seed_assets, seed_wallets, seed_settings):
        """GET /api/tax/whatif/{id} returns comparison data."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        sell_tx = _setup_two_buys_and_sell(db, wallet, btc, run_engine=False)

        resp = client.get(f"/api/tax/whatif/{sell_tx.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "fifo" in data["methods"]
        assert data["most_tax_efficient"] is not None

    def test_whatif_not_found(self, client, db, seed_assets, seed_wallets, seed_settings):
        """GET /api/tax/whatif/99999 returns 404."""
        resp = client.get("/api/tax/whatif/99999")
        assert resp.status_code == 404


class TestSpecificIdAPI:

    def test_apply_specific_id(self, client, db, seed_assets, seed_wallets, seed_settings):
        """POST /api/tax/specific-id/{id} overrides lot selection."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        sell_tx = _setup_two_buys_and_sell(db, wallet, btc)

        # Get the lots
        lots = db.query(TaxLot).filter(
            TaxLot.wallet_id == wallet.id,
            TaxLot.asset_id == btc.id,
        ).all()

        # Find the $35k lot (HIFO choice)
        expensive_lot = max(lots, key=lambda l: Decimal(l.cost_basis_per_unit))

        resp = client.post(
            f"/api/tax/specific-id/{sell_tx.id}",
            json=[{"lot_id": expensive_lot.id, "amount": "1.0"}],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["assignments"]) == 1
        assert Decimal(data["assignments"][0]["gain_loss_usd"]) == Decimal("-5000.00")

    def test_specific_id_wrong_amount(self, client, db, seed_assets, seed_wallets, seed_settings):
        """Specific ID with wrong total amount returns 422."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        sell_tx = _setup_two_buys_and_sell(db, wallet, btc)

        lots = db.query(TaxLot).filter(
            TaxLot.wallet_id == wallet.id,
            TaxLot.asset_id == btc.id,
        ).all()

        resp = client.post(
            f"/api/tax/specific-id/{sell_tx.id}",
            json=[{"lot_id": lots[0].id, "amount": "0.5"}],  # only 0.5 of 1.0
        )
        assert resp.status_code == 422

    def test_specific_id_not_found(self, client, db, seed_assets, seed_wallets, seed_settings):
        """Specific ID on non-existent transaction returns 404."""
        resp = client.post(
            "/api/tax/specific-id/99999",
            json=[{"lot_id": 1, "amount": "1.0"}],
        )
        assert resp.status_code == 404
