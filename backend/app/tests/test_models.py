"""Epic 1 smoke tests — verify schema, models, API health, and seed data."""

from datetime import datetime, timezone

from app.models import (
    Asset, Wallet, Transaction, TaxLot, LotAssignment, Setting,
    TransactionType, WalletType, CostBasisMethod,
    ACQUISITION_TYPES, DISPOSAL_TYPES,
)
from app.tests.conftest import make_transaction


# ---------------------------------------------------------------------------
# Model creation tests
# ---------------------------------------------------------------------------

class TestModels:
    def test_create_wallet(self, db):
        w = Wallet(name="Test Wallet", type="exchange", provider="test")
        db.add(w)
        db.commit()
        db.refresh(w)
        assert w.id is not None
        assert w.name == "Test Wallet"
        assert w.created_at is not None

    def test_create_asset(self, db):
        a = Asset(symbol="BTC", name="Bitcoin", is_fiat=False, coingecko_id="bitcoin")
        db.add(a)
        db.commit()
        db.refresh(a)
        assert a.id is not None
        assert a.symbol == "BTC"

    def test_create_transaction(self, db, seed_wallets, seed_assets):
        tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 3, 15, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=seed_wallets["Coinbase"].id,
            to_amount="1.0",
            to_asset_id=seed_assets["BTC"].id,
            from_amount="30000.00",
            from_asset_id=seed_assets["USD"].id,
            to_value_usd="30000.00",
        )
        assert tx.id is not None
        assert tx.type == "buy"
        assert tx.to_amount == "1.0"

    def test_create_tax_lot(self, db, seed_wallets, seed_assets):
        tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 10, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=seed_wallets["Coinbase"].id,
            to_amount="2.0",
            to_asset_id=seed_assets["BTC"].id,
            to_value_usd="60000.00",
        )
        lot = TaxLot(
            wallet_id=seed_wallets["Coinbase"].id,
            asset_id=seed_assets["BTC"].id,
            amount="2.0",
            remaining_amount="2.0",
            cost_basis_usd="60000.00",
            cost_basis_per_unit="30000.00",
            acquired_date=tx.datetime_utc,
            acquisition_tx_id=tx.id,
            source_type="purchase",
        )
        db.add(lot)
        db.commit()
        db.refresh(lot)
        assert lot.id is not None
        assert lot.remaining_amount == "2.0"
        assert lot.is_fully_disposed is False

    def test_create_lot_assignment(self, db, seed_wallets, seed_assets):
        buy_tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 10, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=seed_wallets["Coinbase"].id,
            to_amount="1.0",
            to_asset_id=seed_assets["BTC"].id,
            to_value_usd="30000.00",
        )
        lot = TaxLot(
            wallet_id=seed_wallets["Coinbase"].id,
            asset_id=seed_assets["BTC"].id,
            amount="1.0",
            remaining_amount="1.0",
            cost_basis_usd="30000.00",
            cost_basis_per_unit="30000.00",
            acquired_date=buy_tx.datetime_utc,
            acquisition_tx_id=buy_tx.id,
            source_type="purchase",
        )
        db.add(lot)
        db.commit()

        sell_tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 6, 15, tzinfo=timezone.utc),
            tx_type="sell",
            from_wallet_id=seed_wallets["Coinbase"].id,
            from_amount="1.0",
            from_asset_id=seed_assets["BTC"].id,
            from_value_usd="40000.00",
        )

        assignment = LotAssignment(
            disposal_tx_id=sell_tx.id,
            tax_lot_id=lot.id,
            amount="1.0",
            cost_basis_usd="30000.00",
            proceeds_usd="40000.00",
            gain_loss_usd="10000.00",
            holding_period="short_term",
            cost_basis_method="fifo",
            tax_year=2025,
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        assert assignment.gain_loss_usd == "10000.00"


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------

class TestEnums:
    def test_transaction_types_cover_all(self):
        assert len(TransactionType) == 16

    def test_acquisition_disposal_no_overlap(self):
        assert ACQUISITION_TYPES.isdisjoint(DISPOSAL_TYPES)

    def test_cost_basis_methods(self):
        assert set(CostBasisMethod) == {"fifo", "lifo", "hifo", "specific_id"}


# ---------------------------------------------------------------------------
# Seed fixture tests
# ---------------------------------------------------------------------------

class TestSeedData:
    def test_seed_assets(self, seed_assets):
        assert len(seed_assets) == 6
        assert "BTC" in seed_assets
        assert seed_assets["USD"].is_fiat is True

    def test_seed_wallets(self, seed_wallets):
        assert len(seed_wallets) == 4
        assert seed_wallets["Coinbase"].type == "exchange"
        assert seed_wallets["Ledger"].type == "hardware"

    def test_seed_settings(self, db, seed_settings):
        s = db.get(Setting, "default_cost_basis_method")
        assert s is not None
        assert s.value == "fifo"
