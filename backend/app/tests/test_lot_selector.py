"""Tests for lot selection algorithms — FIFO, LIFO, HIFO, Specific ID."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.models import TaxLot
from app.services.lot_selector import (
    select_fifo, select_lifo, select_hifo, select_specific_id,
    get_lot_selector, InsufficientLotsError,
)


def _make_lot(db, wallet_id, asset_id, amount, per_unit, acquired_date, tx_id):
    """Helper to create a TaxLot in the DB."""
    lot = TaxLot(
        wallet_id=wallet_id,
        asset_id=asset_id,
        amount=str(amount),
        remaining_amount=str(amount),
        cost_basis_usd=str(Decimal(str(amount)) * Decimal(str(per_unit))),
        cost_basis_per_unit=str(per_unit),
        acquired_date=acquired_date,
        acquisition_tx_id=tx_id,
        source_type="purchase",
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


class TestFIFO:
    def test_consumes_oldest_first(self, db, seed_wallets, seed_assets):
        w = seed_wallets["Coinbase"]
        a = seed_assets["BTC"]
        # Create a dummy transaction for FK
        from app.tests.conftest import make_transaction
        tx = make_transaction(db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
                              tx_type="buy", to_wallet_id=w.id, to_amount="1")

        lot1 = _make_lot(db, w.id, a.id, "1.0", "20000", datetime(2025, 1, 1), tx.id)
        lot2 = _make_lot(db, w.id, a.id, "1.0", "30000", datetime(2025, 2, 1), tx.id)
        lot3 = _make_lot(db, w.id, a.id, "1.0", "25000", datetime(2025, 3, 1), tx.id)

        result = select_fifo([lot1, lot2, lot3], Decimal("1.0"))
        assert len(result) == 1
        assert result[0].lot.id == lot1.id
        assert result[0].amount == Decimal("1.0")

    def test_spans_multiple_lots(self, db, seed_wallets, seed_assets):
        w = seed_wallets["Coinbase"]
        a = seed_assets["BTC"]
        from app.tests.conftest import make_transaction
        tx = make_transaction(db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
                              tx_type="buy", to_wallet_id=w.id, to_amount="1")

        lot1 = _make_lot(db, w.id, a.id, "0.5", "20000", datetime(2025, 1, 1), tx.id)
        lot2 = _make_lot(db, w.id, a.id, "1.0", "30000", datetime(2025, 2, 1), tx.id)

        result = select_fifo([lot1, lot2], Decimal("1.0"))
        assert len(result) == 2
        assert result[0].lot.id == lot1.id
        assert result[0].amount == Decimal("0.5")
        assert result[1].lot.id == lot2.id
        assert result[1].amount == Decimal("0.5")


class TestLIFO:
    def test_consumes_newest_first(self, db, seed_wallets, seed_assets):
        w = seed_wallets["Coinbase"]
        a = seed_assets["BTC"]
        from app.tests.conftest import make_transaction
        tx = make_transaction(db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
                              tx_type="buy", to_wallet_id=w.id, to_amount="1")

        lot1 = _make_lot(db, w.id, a.id, "1.0", "20000", datetime(2025, 1, 1), tx.id)
        lot2 = _make_lot(db, w.id, a.id, "1.0", "30000", datetime(2025, 2, 1), tx.id)
        lot3 = _make_lot(db, w.id, a.id, "1.0", "25000", datetime(2025, 3, 1), tx.id)

        result = select_lifo([lot1, lot2, lot3], Decimal("1.0"))
        assert len(result) == 1
        assert result[0].lot.id == lot3.id


class TestHIFO:
    def test_consumes_highest_cost_first(self, db, seed_wallets, seed_assets):
        w = seed_wallets["Coinbase"]
        a = seed_assets["BTC"]
        from app.tests.conftest import make_transaction
        tx = make_transaction(db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
                              tx_type="buy", to_wallet_id=w.id, to_amount="1")

        lot1 = _make_lot(db, w.id, a.id, "1.0", "20000", datetime(2025, 1, 1), tx.id)
        lot2 = _make_lot(db, w.id, a.id, "1.0", "30000", datetime(2025, 2, 1), tx.id)
        lot3 = _make_lot(db, w.id, a.id, "1.0", "25000", datetime(2025, 3, 1), tx.id)

        result = select_hifo([lot1, lot2, lot3], Decimal("1.0"))
        assert len(result) == 1
        assert result[0].lot.id == lot2.id
        assert result[0].cost_basis_usd == Decimal("30000.00")


class TestPartialConsumption:
    def test_partial_lot(self, db, seed_wallets, seed_assets):
        w = seed_wallets["Coinbase"]
        a = seed_assets["BTC"]
        from app.tests.conftest import make_transaction
        tx = make_transaction(db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
                              tx_type="buy", to_wallet_id=w.id, to_amount="1")

        lot = _make_lot(db, w.id, a.id, "2.0", "30000", datetime(2025, 1, 1), tx.id)

        result = select_fifo([lot], Decimal("0.5"))
        assert len(result) == 1
        assert result[0].amount == Decimal("0.5")
        assert result[0].cost_basis_usd == Decimal("15000.00")


class TestInsufficientLots:
    def test_raises_on_insufficient(self, db, seed_wallets, seed_assets):
        w = seed_wallets["Coinbase"]
        a = seed_assets["BTC"]
        from app.tests.conftest import make_transaction
        tx = make_transaction(db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
                              tx_type="buy", to_wallet_id=w.id, to_amount="1")

        lot = _make_lot(db, w.id, a.id, "1.0", "30000", datetime(2025, 1, 1), tx.id)

        with pytest.raises(InsufficientLotsError):
            select_fifo([lot], Decimal("2.0"))


class TestSpecificID:
    def test_selects_specific_lot(self, db, seed_wallets, seed_assets):
        w = seed_wallets["Coinbase"]
        a = seed_assets["BTC"]
        from app.tests.conftest import make_transaction
        tx = make_transaction(db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
                              tx_type="buy", to_wallet_id=w.id, to_amount="1")

        lot1 = _make_lot(db, w.id, a.id, "1.0", "20000", datetime(2025, 1, 1), tx.id)
        lot2 = _make_lot(db, w.id, a.id, "1.0", "30000", datetime(2025, 2, 1), tx.id)
        lot3 = _make_lot(db, w.id, a.id, "1.0", "25000", datetime(2025, 3, 1), tx.id)

        result = select_specific_id([lot1, lot2, lot3], [(lot2.id, Decimal("1.0"))])
        assert len(result) == 1
        assert result[0].lot.id == lot2.id

    def test_rejects_nonexistent_lot(self, db, seed_wallets, seed_assets):
        w = seed_wallets["Coinbase"]
        a = seed_assets["BTC"]
        from app.tests.conftest import make_transaction
        tx = make_transaction(db, datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
                              tx_type="buy", to_wallet_id=w.id, to_amount="1")

        lot = _make_lot(db, w.id, a.id, "1.0", "30000", datetime(2025, 1, 1), tx.id)

        with pytest.raises(ValueError, match="not found"):
            select_specific_id([lot], [(9999, Decimal("1.0"))])


class TestGetLotSelector:
    def test_known_methods(self):
        assert get_lot_selector("fifo") == select_fifo
        assert get_lot_selector("lifo") == select_lifo
        assert get_lot_selector("hifo") == select_hifo

    def test_unknown_method(self):
        with pytest.raises(ValueError, match="Unknown"):
            get_lot_selector("mystery")
