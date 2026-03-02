"""Tests for the delete-import feature (undo an import).

Covers:
 - DELETE /api/import/logs/{id} endpoint
 - import_log_id is set on transactions during CSV and Koinly imports
 - Deleting an import removes transactions, tax lots, and lot assignments
 - Tax recalculation runs after deletion
 - Edge cases: 404 for missing log, empty import, partial deletion
"""

from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO

import pytest

from app.models import Transaction, ImportLog, TaxLot, LotAssignment, Setting
from app.services.tax_engine import recalculate_all
from app.tests.conftest import make_transaction


KOINLY_CSV = """\
Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash
2025-01-15 10:00:00 UTC,,,1.0,BTC,,,30000.00,USD,,Bought BTC,hash001
2025-02-15 12:00:00 UTC,,,2.0,ETH,,,6000.00,USD,,Bought ETH,hash002
"""

SELL_CSV = """\
Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash
2025-06-15 14:00:00 UTC,0.5,BTC,,,,,,USD,,Sold BTC,hash003
"""


# ---------------------------------------------------------------------------
# Helper: do a full upload+confirm cycle, return the confirm response data
# ---------------------------------------------------------------------------

def _import_csv(client, csv_content: str, wallet_id: int) -> dict:
    """Upload a CSV and confirm it. Returns the confirm response JSON."""
    upload = client.post(
        "/api/import/csv",
        files={"file": ("test.csv", BytesIO(csv_content.encode()), "text/csv")},
    )
    assert upload.status_code == 200
    rows = upload.json()["rows"]
    row_nums = [r["row_number"] for r in rows if r["status"] != "error"]
    confirm = client.post(
        "/api/import/csv/confirm",
        json={"wallet_id": wallet_id, "rows": row_nums},
    )
    assert confirm.status_code == 200
    return confirm.json()


# ---------------------------------------------------------------------------
# Tests: import_log_id linkage
# ---------------------------------------------------------------------------


class TestImportLogLinkage:
    """Verify that transactions get their import_log_id set during import."""

    def test_csv_import_sets_import_log_id(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        wallet = seed_wallets["Coinbase"]
        data = _import_csv(client, KOINLY_CSV, wallet.id)

        log_id = data["import_log_id"]
        txs = db.query(Transaction).filter_by(import_log_id=log_id).all()
        assert len(txs) == data["transactions_imported"]
        assert all(tx.import_log_id == log_id for tx in txs)

    def test_manual_transactions_have_no_import_log_id(
        self, db, seed_assets, seed_wallets, seed_settings
    ):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=w.id,
            to_amount="1.0",
            to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        assert tx.import_log_id is None


# ---------------------------------------------------------------------------
# Tests: DELETE endpoint
# ---------------------------------------------------------------------------


class TestDeleteImport:
    """DELETE /api/import/logs/{id} removes the import and its transactions."""

    def test_delete_removes_transactions(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        wallet = seed_wallets["Coinbase"]
        data = _import_csv(client, KOINLY_CSV, wallet.id)
        log_id = data["import_log_id"]
        imported_count = data["transactions_imported"]
        assert imported_count >= 1

        # Verify transactions exist
        assert db.query(Transaction).filter_by(import_log_id=log_id).count() == imported_count

        # Delete
        resp = client.delete(f"/api/import/logs/{log_id}")
        assert resp.status_code == 200
        result = resp.json()
        assert result["deleted"] is True
        assert result["transactions_deleted"] == imported_count

        # Verify transactions are gone
        assert db.query(Transaction).filter_by(import_log_id=log_id).count() == 0

    def test_delete_removes_import_log(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        wallet = seed_wallets["Coinbase"]
        data = _import_csv(client, KOINLY_CSV, wallet.id)
        log_id = data["import_log_id"]

        client.delete(f"/api/import/logs/{log_id}")

        assert db.query(ImportLog).filter_by(id=log_id).first() is None

    def test_delete_removes_tax_lots(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """Importing buys creates tax lots; deleting the import removes them."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        data = _import_csv(client, KOINLY_CSV, wallet.id)
        log_id = data["import_log_id"]

        # Run tax engine so tax lots are created
        recalculate_all(db)

        tx_ids = [
            tx.id
            for tx in db.query(Transaction).filter_by(import_log_id=log_id).all()
        ]
        lots_before = (
            db.query(TaxLot)
            .filter(TaxLot.acquisition_tx_id.in_(tx_ids))
            .count()
        )
        assert lots_before >= 1

        # Delete the import
        resp = client.delete(f"/api/import/logs/{log_id}")
        assert resp.status_code == 200

        # Tax lots for those transactions should be gone
        lots_after = (
            db.query(TaxLot)
            .filter(TaxLot.acquisition_tx_id.in_(tx_ids))
            .count()
        )
        assert lots_after == 0

    def test_delete_removes_lot_assignments(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """Import buys + sells, then delete the sell import.

        The lot assignments (gains/losses) from the sell should be removed.
        """
        wallet = seed_wallets["Coinbase"]

        # Import buys
        buy_data = _import_csv(client, KOINLY_CSV, wallet.id)
        buy_log_id = buy_data["import_log_id"]

        # Import sells
        sell_data = _import_csv(client, SELL_CSV, wallet.id)
        sell_log_id = sell_data["import_log_id"]

        # Run tax engine
        recalculate_all(db)

        sell_tx_ids = [
            tx.id
            for tx in db.query(Transaction).filter_by(import_log_id=sell_log_id).all()
        ]
        assignments_before = (
            db.query(LotAssignment)
            .filter(LotAssignment.disposal_tx_id.in_(sell_tx_ids))
            .count()
        )
        assert assignments_before >= 1

        # Delete the sell import
        resp = client.delete(f"/api/import/logs/{sell_log_id}")
        assert resp.status_code == 200

        # Lot assignments for those sell transactions should be gone
        assignments_after = (
            db.query(LotAssignment)
            .filter(LotAssignment.disposal_tx_id.in_(sell_tx_ids))
            .count()
        )
        assert assignments_after == 0

        # Buy transactions should still exist
        assert db.query(Transaction).filter_by(import_log_id=buy_log_id).count() >= 1

    def test_delete_does_not_affect_other_imports(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """Deleting one import doesn't touch transactions from another."""
        wallet = seed_wallets["Coinbase"]

        data1 = _import_csv(client, KOINLY_CSV, wallet.id)
        log_id1 = data1["import_log_id"]
        count1 = data1["transactions_imported"]

        other_csv = """\
Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash
2025-03-01 09:00:00 UTC,,,5.0,SOL,,,500.00,USD,,Bought SOL,hash_other
"""
        data2 = _import_csv(client, other_csv, wallet.id)
        log_id2 = data2["import_log_id"]
        count2 = data2["transactions_imported"]

        # Delete first import
        client.delete(f"/api/import/logs/{log_id1}")

        # Second import's transactions remain
        remaining = db.query(Transaction).filter_by(import_log_id=log_id2).count()
        assert remaining == count2

    def test_delete_does_not_affect_manual_transactions(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """Manual transactions (no import_log_id) are untouched by delete."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        manual_tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_amount="1.0",
            to_asset_id=btc.id,
            to_value_usd="50000.00",
        )

        data = _import_csv(client, KOINLY_CSV, wallet.id)
        log_id = data["import_log_id"]

        client.delete(f"/api/import/logs/{log_id}")

        # Manual transaction still exists
        assert db.query(Transaction).filter_by(id=manual_tx.id).first() is not None


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestDeleteImportEdgeCases:

    def test_delete_nonexistent_returns_404(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        resp = client.delete("/api/import/logs/99999")
        assert resp.status_code == 404

    def test_delete_already_deleted_returns_404(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        wallet = seed_wallets["Coinbase"]
        data = _import_csv(client, KOINLY_CSV, wallet.id)
        log_id = data["import_log_id"]

        # First delete succeeds
        resp1 = client.delete(f"/api/import/logs/{log_id}")
        assert resp1.status_code == 200

        # Second delete returns 404
        resp2 = client.delete(f"/api/import/logs/{log_id}")
        assert resp2.status_code == 404

    def test_delete_import_updates_logs_list(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """After deletion, GET /api/import/logs no longer shows the import."""
        wallet = seed_wallets["Coinbase"]
        data = _import_csv(client, KOINLY_CSV, wallet.id)
        log_id = data["import_log_id"]

        # Logs should include this import
        logs_before = client.get("/api/import/logs").json()
        log_ids_before = [l["id"] for l in logs_before["items"]]
        assert log_id in log_ids_before

        # Delete
        client.delete(f"/api/import/logs/{log_id}")

        # Logs should not include it anymore
        logs_after = client.get("/api/import/logs").json()
        log_ids_after = [l["id"] for l in logs_after["items"]]
        assert log_id not in log_ids_after

    def test_delete_triggers_recalculation(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """After deleting a buy import, a subsequent sell should have no lot to match."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Import buys
        buy_data = _import_csv(client, KOINLY_CSV, wallet.id)
        buy_log_id = buy_data["import_log_id"]

        # Manually add a sell (not part of any import)
        make_transaction(
            db,
            datetime_utc=datetime(2025, 7, 1, tzinfo=timezone.utc),
            tx_type="sell",
            from_wallet_id=wallet.id,
            from_amount="0.5",
            from_asset_id=btc.id,
            from_value_usd="20000.00",
        )

        # Run tax calc — should work fine with buys available
        recalculate_all(db)
        lots = db.query(TaxLot).filter_by(wallet_id=wallet.id, asset_id=btc.id).all()
        assert len(lots) >= 1

        # Delete the buy import — removes the BTC buy
        client.delete(f"/api/import/logs/{buy_log_id}")

        # After delete + recalc, the BTC tax lots from the import should be gone
        lots_after = db.query(TaxLot).filter_by(
            wallet_id=wallet.id, asset_id=btc.id
        ).all()
        # The only lots remaining would be from the sell's error state (no lots to consume)
        buy_lots = [l for l in lots_after if l.source_type == "purchase"]
        assert len(buy_lots) == 0
