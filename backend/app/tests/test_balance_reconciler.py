"""Tests for balance_reconciler — balance reconciliation between tx history and lots."""

from datetime import datetime, timezone
from decimal import Decimal

from app.services.balance_reconciler import reconcile_balances
from app.tests.factories import create_asset, create_wallet, create_transaction, create_tax_lot


class TestReconcileBalances:
    def test_balanced_wallet(self, db):
        """When lots match transaction history, no discrepancy."""
        wallet = create_wallet(db, name="Coinbase")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        tx = create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=btc.id,
            to_amount="1.0",
        )
        db.commit()

        create_tax_lot(
            db,
            wallet_id=wallet.id,
            asset_id=btc.id,
            amount="1.0",
            cost_basis_usd="50000.00",
            acquisition_tx_id=tx.id,
        )
        db.commit()

        results = reconcile_balances(db)
        assert len(results) == 1
        assert results[0]["is_discrepancy"] is False
        assert results[0]["wallet_name"] == "Coinbase"
        assert results[0]["asset_symbol"] == "BTC"

    def test_imbalanced_wallet(self, db):
        """When lot balance doesn't match tx history, discrepancy flagged."""
        wallet = create_wallet(db, name="Ledger")
        eth = create_asset(db, symbol="ETH")
        db.commit()

        tx = create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=eth.id,
            to_amount="5.0",
        )
        db.commit()

        # Lot has only 3.0 instead of 5.0
        create_tax_lot(
            db,
            wallet_id=wallet.id,
            asset_id=eth.id,
            amount="3.0",
            cost_basis_usd="9000.00",
            acquisition_tx_id=tx.id,
        )
        db.commit()

        results = reconcile_balances(db)
        assert len(results) == 1
        assert results[0]["is_discrepancy"] is True
        assert Decimal(results[0]["difference"]) == Decimal("2.0")

    def test_empty_wallet(self, db):
        """Wallet with no lots returns no results."""
        create_wallet(db, name="Empty")
        create_asset(db, symbol="BTC")
        db.commit()

        results = reconcile_balances(db)
        assert len(results) == 0

    def test_multiple_assets(self, db):
        """Multiple assets in one wallet are reconciled separately."""
        wallet = create_wallet(db, name="Multi")
        btc = create_asset(db, symbol="BTC")
        eth = create_asset(db, symbol="ETH")
        db.commit()

        tx1 = create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=btc.id,
            to_amount="1.0",
        )
        tx2 = create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 2, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=eth.id,
            to_amount="10.0",
        )
        db.commit()

        create_tax_lot(db, wallet_id=wallet.id, asset_id=btc.id, amount="1.0",
                       cost_basis_usd="50000.00", acquisition_tx_id=tx1.id)
        create_tax_lot(db, wallet_id=wallet.id, asset_id=eth.id, amount="10.0",
                       cost_basis_usd="30000.00", acquisition_tx_id=tx2.id)
        db.commit()

        results = reconcile_balances(db)
        assert len(results) == 2
        assert all(r["is_discrepancy"] is False for r in results)
